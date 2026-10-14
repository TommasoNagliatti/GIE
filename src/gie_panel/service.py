"""Interactive runs own new directories. Replay never enters alert or MPC paths."""
import copy,json,threading,uuid
from pathlib import Path
import pandas as pd
from gie_multistation.manager import Manager,StationError
from gie_provisioning.examples import sample
from .alerts import Alerts,condition,detect,key,now
from .data import *

class PanelService:
    def __init__(self,manager,directory):
        self.manager=manager;self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        if NEW not in manager.configs:
            from gie_provisioning.examples import fixture
            manager.provision(fixture())
        self.write_lock=threading.RLock()
        self.alerts=Alerts(self.directory/'alerts.sqlite');self.runs={};self.locks={sid:threading.RLock() for sid in manager.configs}
        self.index=self.directory/'runs.json'
        saved=json.loads(self.index.read_text()) if self.index.exists() else {}
        for sid,run in saved.items():
            if sid in manager.configs and len(run['id'])==32 and all(x in '0123456789abcdef' for x in run['id']):self.runs[sid]=dict(run,manager=None)
    def close(self):
        for run in self.runs.values():
            if run.get('manager'):run['manager'].close()
        self.alerts.close()
    def _save(self):
        with self.write_lock:
            fields=('id','scenario','index','history','generation','stopped','scene_marker','scene_sequence')
            raw={s:{k:copy.deepcopy(r[k]) for k in fields if k in r} for s,r in list(self.runs.items())}
            temp=self.index.with_suffix('.tmp');temp.write_text(json.dumps(raw),encoding='utf-8');temp.replace(self.index)
    def _manager(self,sid,run):
        if run.get('manager') is None:
            m=Manager(self.directory/'runs'/run['id'],timeout=90)
            cfg=self.manager.configs[sid]
            if cfg['kind']=='baseline' and sid not in m.configs:m.provision(cfg['technical'])
            run['manager']=m
        return run['manager']
    def reset(self,sid,scenario):
        with self.locks[sid]:
            if scenario not in {x['id'] for x in catalog(sid)}:raise ValueError('Unknown scenario')
            old=self.runs.get(sid)
            if old and old.get('manager'):old['manager'].close()
            run=dict(id=uuid.uuid4().hex,scenario=scenario,index=0,history=[],generation=old.get('generation') if old else None,manager=None)
            self.runs[sid]=run;self._save()
            return self.start(sid)
    def start(self,sid):
        with self.locks[sid]:
            if sid not in self.runs:return self.reset(sid,catalog(sid)[0]['id'])
            run=self.runs[sid];reply=self._manager(sid,run).start(sid)
            old=run.get('generation');run['generation']=reply['generation'];run['stopped']=False
            checkpoint=reply.get('simulation_state')
            if checkpoint:run['index']=checkpoint['cycles']
            self._save()
            if old and old!=reply['generation']:
                self.alerts.observe(sid,reply['generation'],now(),'generation:'+reply['generation'],[condition('GENERATION_CHANGED','Processo reiniciado — geração alterada','process','info')],set())
            return self.wrap(sid,reply)
    def wrap(self,sid,reply):
        run=self.runs[sid];r=reply.get('state');view=display(r,self.manager.configs[sid],'INTERACTIVE',run['history']) if r else None
        return dict(view=view,process='running',generation=reply['generation'],model=reply['model_identity'],mode=reply['mode'],presentation=reply['presentation'],run_id=run['id'],scenario=run['scenario'],cycle=run['index'])
    def _source(self,run,reply):
        base=run['id']+':'+reply['generation']
        if reply['mode']!='PRESENTATION':return base+':'+str(reply['revision'])
        marker=str(reply['presentation']['scene_id'])+':'+str(reply['revision'])
        if run.get('scene_marker')!=marker:
            run['scene_marker']=marker;run['scene_sequence']=run.get('scene_sequence',0)+1;self._save()
        return base+':scene:'+str(run['scene_sequence'])
    def state(self,sid):
        with self.locks[sid]:
            run=self.runs.get(sid)
            if not run or run.get('manager') is None or run.get('stopped'):return dict(view=None,process='stopped',cycle=run['index'] if run else 0)
            try:
                reply=run['manager'].request(sid,'state')
                if reply.get('state') and reply['mode']=='PRESENTATION':
                    r=reply['state'];source=self._source(run,reply)
                    active=[key(a['code'],a.get('equipment_id')) for a in self.alerts.list(sid) if a['status']!='RESOLVED']
                    conditions,domains=detect(r,equipment(self.manager.configs[sid]),active=active)
                    self.alerts.observe(sid,reply['generation'],r['timestamp'],source,conditions,domains)
                return self.wrap(sid,reply)
            except StationError:
                self.alerts.observe(sid,run.get('generation'),now(),'lost:'+str(run.get('generation')),[condition('WORKER_ERROR','Worker indisponível','process','error')],set());raise
    def execute(self,sid,op,body):
        with self.locks[sid]:
            if sid not in self.runs or self.runs[sid].get('manager') is None or self.runs[sid].get('stopped'):self.start(sid)
            run=self.runs[sid];m=run['manager'];current=None
            try:
                if op=='cycle':
                    if run['index']>=96:raise ValueError('24h completed; create a new test run')
                    config=self.manager.configs[sid]
                    start=config['default_issue'] if sid==COMM else '2026-10-13T00:00:00-04:00' if sid==NEW else DATES[run['scenario']]
                    issue=(pd.Timestamp(start)+pd.Timedelta(minutes=15*run['index'])).isoformat();payload=dict(issue_time=issue)
                    if config['kind']=='baseline':
                        payload=sample(config['technical'],issue)
                        if body.get('fixture')=='missing':payload={'issue_time':issue}
                        elif body.get('fixture')=='stale':payload['current']['observed_at']=(pd.Timestamp(issue)-pd.Timedelta(hours=1)).isoformat()
                        elif body.get('fixture')=='overload':payload['current']['building_kw']=config['technical']['import_kw']+1000
                        elif body.get('fixture')=='offline':payload['current']['demands'][0]['available']=False
                        current=payload.get('current')
                    reply=m.request(sid,'cycle',payload)
                    if reply['state']['execution_allowed']:run['index']+=1
                elif op=='restart':reply=m.restart(sid)
                elif op=='stop':
                    m.stop(sid);run['stopped']=True;self._save();self.alerts.observe(sid,run['generation'],now(),'stop:'+uuid.uuid4().hex,[condition('PROCESS_STOPPED','Processo GIE parado','process','warning')],set());return dict(view=None,process='stopped',cycle=run['index'])
                else:reply=m.request(sid,op,body)
            except StationError as exc:
                invalid=exc.status==422
                self.alerts.observe(sid,run['generation'],now(),'worker-error:'+uuid.uuid4().hex,[condition('INVALID_DATA' if invalid else 'WORKER_ERROR','Entrada inválida' if invalid else 'Falha ou timeout do worker','data' if invalid else 'process','error',status=exc.status)],set());raise
            old=run.get('generation');run['generation']=reply['generation']
            if old and old!=reply['generation']:self.alerts.observe(sid,reply['generation'],now(),'generation:'+reply['generation'],[condition('GENERATION_CHANGED','Geração do worker alterada','process','info')],set())
            r=reply.get('state')
            if r:
                source=self._source(run,reply)
                active=[key(a['code'],a.get('equipment_id')) for a in self.alerts.list(sid) if a['status']!='RESOLVED']
                conditions,domains=detect(r,equipment(self.manager.configs[sid]),current,active)
                domains.add('process')
                self.alerts.observe(sid,reply['generation'],r['timestamp'],source,conditions,domains)
                if op in ('cycle','manual','presentation'):run['history'].append(history_row(r));run['history']=run['history'][-192:]
            self._save();return self.wrap(sid,reply)

def install(app,authorize):
    from fastapi import Depends,HTTPException
    from pydantic import BaseModel,ConfigDict
    from typing import Literal
    class Run(BaseModel):
        model_config=ConfigDict(extra='forbid')
        scenario:str
    class Cycle(BaseModel):
        model_config=ConfigDict(extra='forbid')
        fixture:Literal['normal','missing','stale','overload','offline']='normal'
    def service(sid):
        p=app.state.panel
        if sid not in p.manager.configs:raise HTTPException(404,'Unknown station')
        return p
    def call(sid,method,*args):
        try:return getattr(service(sid),method)(sid,*args)
        except StationError as exc:raise HTTPException(exc.status,str(exc)) from exc
        except (ValueError,KeyError) as exc:raise HTTPException(422,str(exc)) from exc
    @app.get('/panel/{station_id}/catalog')
    def choices(sid=Depends(authorize)):
        p=service(sid);return dict(scenarios=catalog(sid),equipment=equipment(p.manager.configs[sid]),name=NAMES.get(sid,sid))
    @app.get('/panel/{station_id}/replay')
    def replay_data(scenario:str,index:int=0,sid=Depends(authorize)):
        p=service(sid);cfg=p.manager.configs[sid]
        try:
            frames=replay(sid,scenario,json.dumps(cfg,sort_keys=True))
            if not 0<=index<len(frames):raise ValueError('Replay index out of range')
            return dict(view=display(frames[index],cfg,'REPLAY',[history_row(r) for r in frames[:index+1]]),cycle=index+1,total=len(frames),process='replay',mode='REPLAY',model='Artefatos salvos')
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    @app.post('/panel/{station_id}/reset')
    def reset(body:Run,sid=Depends(authorize)):return call(sid,'reset',body.scenario)
    @app.post('/panel/{station_id}/initialize')
    def start(sid=Depends(authorize)):return call(sid,'start')
    @app.get('/panel/{station_id}/state')
    def state(sid=Depends(authorize)):return call(sid,'state')
    @app.post('/panel/{station_id}/cycle')
    def cycle(body:Cycle,sid=Depends(authorize)):return call(sid,'execute','cycle',body.model_dump())
    from gie_multistation.api import Mode,Presentation,Event
    @app.post('/panel/{station_id}/mode')
    def mode(body:Mode,sid=Depends(authorize)):return call(sid,'execute','mode',body.model_dump())
    @app.post('/panel/{station_id}/presentation')
    def presentation(body:Presentation,sid=Depends(authorize)):return call(sid,'execute','presentation',body.model_dump())
    @app.post('/panel/{station_id}/manual')
    def manual(body:Event,sid=Depends(authorize)):return call(sid,'execute','manual',body.model_dump())
    @app.post('/panel/{station_id}/restart')
    def restart(sid=Depends(authorize)):return call(sid,'execute','restart',{})
    @app.post('/panel/{station_id}/stop')
    def stop(sid=Depends(authorize)):return call(sid,'execute','stop',{})
    @app.get('/panel/{station_id}/alerts')
    def alerts(severity:str|None=None,status:str|None=None,equipment_id:str|None=None,sid=Depends(authorize)):return service(sid).alerts.list(sid,severity,status,equipment_id)
    @app.post('/panel/{station_id}/alerts/{alert_id}/ack')
    def ack(alert_id:str,sid=Depends(authorize)):
        try:return service(sid).alerts.ack(sid,alert_id)
        except KeyError as exc:raise HTTPException(404,'Unknown station alert') from exc
    @app.get('/panel/{station_id}/events')
    def events(after:int=0,sid=Depends(authorize)):return service(sid).alerts.history(sid,after)
    @app.get('/panel/{station_id}/comparison')
    def comparison(sid=Depends(authorize)):
        service(sid)
        if sid!='DEMO_CASA_001':raise HTTPException(404,'Residential comparison only')
        from gie_panel.comparison import OUT
        saved=OUT/'result.json'
        if saved.is_file():return dict(status='complete',result=json.loads(saved.read_text(encoding='utf-8')))
        progress=OUT/'progress.json'
        return json.loads(progress.read_text(encoding='utf-8')) if progress.is_file() else dict(status='not_run')
