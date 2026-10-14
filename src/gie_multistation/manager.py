"""One spawned process and serialized mailbox per station; no inherited state."""
import copy
import json
import multiprocessing as mp
import os
from pathlib import Path
import threading
import time
import uuid
from .registry import registry


class StationError(RuntimeError):
    def __init__(self, detail, status=409):
        super().__init__(detail); self.status=status


def worker(config, connection, directory, generation):
    from .engines import make_control, local_time
    from gie_runtime.models import json_safe
    os.chdir(directory)  # Any unexpected relative cache is still private to this worker.
    try:
        control=make_control(config)
        last_issue=getattr(control.engine,'last_issue',None);revision=0;history=[]
        def state():
            result=control.get_state()
            return dict(station_id=config['station_id'],schema_version='1.0',pid=os.getpid(),generation=generation,
                revision=revision,mode=control.get_mode(),state=result,presentation=control.get_presentation_state(),
                simulation_state=control.engine.energy_state_view() if hasattr(control.engine,'energy_state_view') else None,
                capabilities=dict(forecasts=True,mpc_demo=True,physical_dispatch=False,
                    load_balancer=True,presentation=config['kind']=='commercial',
                    manual_demo=config['kind']=='commercial'),
                model_identity=control.engine.model_identity,source='SIMULATED',hardware_commands_sent=False,
                recovery='Fresh process: no previous commands or telemetry replayed; initialize/cycle required.',
                history=copy.deepcopy(history),cache=copy.deepcopy(control.engine.cache),
                messages=copy.deepcopy(control.message_history))
        connection.send({'ok':True,'result':state()})
    except Exception as exc:
        connection.send({'ok':False,'detail':str(exc),'status':503});connection.close();return
    while True:
        try:
            request=connection.recv()
        except EOFError:
            break
        op=request['op'];body=request.get('body',{})
        if op=='shutdown':break
        try:
            if op=='state':
                control.tick()
            elif op=='mode':
                mode=body['mode']
                if config['kind']!='commercial' and mode in ('PRESENTATION','MANUAL_DEMO'):
                    raise ValueError('Original scenes/manual physics only compatible with commercial profile')
                control.set_mode(mode);revision+=1
            elif op=='cycle':
                default_issue=(last_issue+__import__('datetime').timedelta(minutes=15)) if last_issue is not None and hasattr(control.engine,'simulation') else config['default_issue']
                if config['kind']=='baseline':
                    from gie_provisioning.engine import timestamp
                    issue=timestamp(body.get('issue_time') or default_issue,config['timezone'],True)
                else:issue=local_time(body.get('issue_time') or default_issue)
                if last_issue is not None and issue<=last_issue:
                    raise ValueError('Replay/out-of-order cycle; use a later issue_time')
                result=control.run_cycle(issue,body.get('current'))
                if not hasattr(control.engine,'simulation') or result['execution_allowed']:last_issue=issue
                revision+=1
                history.append(dict(station_id=config['station_id'],issue_time=issue.isoformat(),origin='SIMULATED',status=result['status']))
                history=history[-100:]
            elif op=='presentation':
                if config['kind']!='commercial':raise ValueError('Presentation is commercial-only')
                action=body['action']
                if action=='scene':control.set_scene(body['scene_id'])
                elif action=='interval':control.set_presentation_interval(body['seconds'])
                elif action=='loop':control.set_loop(body['enabled'])
                else:
                    methods={'start':control.start_presentation,'pause':control.pause_presentation,'resume':control.resume_presentation,
                             'stop':control.stop_presentation,'reset':control.stop_presentation,'next':control.next_scene,'previous':control.previous_scene}
                    if action not in methods:raise ValueError('Unknown presentation action')
                    methods[action]()
                revision+=1
            elif op=='manual':
                if config['kind']!='commercial':raise ValueError('Manual demo is commercial-only')
                if body['event']=='RESET':control.reset_demo()
                else:control.trigger_demo_event(body['event'])
                revision+=1
            else:raise ValueError('Unknown worker operation')
            response=state()
            if op!='state':
                # Audit only. Deliberately not restored as authoritative operational state.
                audit=dict(station_id=config['station_id'],generation=generation,revision=revision,op=op,mode=control.mode,
                           pid=os.getpid(),origin='SIMULATED',hardware_commands_sent=False)
                with open('events.jsonl','a',encoding='utf-8') as f:f.write(json.dumps(audit)+'\n')
                temp=Path('snapshot.tmp');temp.write_text(json.dumps(json_safe(response),allow_nan=False),encoding='utf-8');temp.replace('snapshot.json')
            connection.send({'ok':True,'result':json_safe(response)})
        except (ValueError,KeyError,TypeError) as exc:
            connection.send({'ok':False,'status':422,'detail':str(exc)})
        except Exception as exc:
            # Unexpected errors make this incarnation unusable. No stale result is served.
            connection.send({'ok':False,'status':503,'detail':type(exc).__name__+': '+str(exc)})
            break
    connection.close()


class Manager:
    def __init__(self, data_dir, timeout=90):
        self.configs=registry();self.directory=Path(data_dir).resolve();self.directory.mkdir(parents=True,exist_ok=True)
        self.timeout=timeout;self.context=mp.get_context('spawn');self.closed=False
        self.slots={sid:dict(lock=threading.RLock(),process=None,pipe=None,generation=None,error=None) for sid in self.configs}
        # Prevent two API instances/uvicorn workers sharing station journals.
        self.owner=open(self.directory/'manager.lock','a+b');self.owner.seek(0);self.owner.write(b'0');self.owner.flush();self.owner.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.owner.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.owner.close();raise RuntimeError('Another manager owns this runtime directory')
        self.registry_lock=threading.RLock()
        try:
            from gie_provisioning.store import load
            for sid,config in load(self.directory).items():
                if sid.casefold() in {s.casefold() for s in self.configs}:raise ValueError('Duplicate persisted station')
                self.configs[sid]=config
                self.slots[sid]=dict(lock=threading.RLock(),process=None,pipe=None,generation=None,error=None)
        except Exception:
            self.owner.close();raise

    def provision(self,technical):
        from gie_provisioning.contracts import Provision
        from gie_provisioning.store import save
        technical=Provision.model_validate(technical)
        with self.registry_lock:
            if self.closed:raise StationError('Manager is closed',503)
            sid=technical.station_id
            existing=next((s for s in self.configs if s.casefold()==sid.casefold()),None)
            if existing is not None:
                if existing==sid and self.configs[sid].get('technical')==technical.model_dump():return copy.deepcopy(self.configs[sid])
                raise StationError('Station already registered; technical replacement forbidden',409)
            folder=self.directory/sid
            if folder.exists():raise StationError('Existing station directory requires operator review',409)
            folder.mkdir()
            for name in ('models','history','cache'): (folder/name).mkdir()
            from gie_provisioning.contracts import ModelState
            (folder/'models'/'registry.json').write_text(json.dumps(ModelState(station_id=sid).model_dump()),encoding='utf-8')
            config=save(self.directory,technical)
            self.configs[sid]=config
            self.slots[sid]=dict(lock=threading.RLock(),process=None,pipe=None,generation=None,error=None)
            return copy.deepcopy(config)

    def slot(self,sid):
        if sid not in self.slots:raise StationError('Unknown station',404)
        if self.closed:raise StationError('Manager is closed',503)
        return self.slots[sid]

    def health(self,sid):
        s=self.slot(sid)
        with s['lock']:
            p=s['process'];alive=p is not None and p.is_alive()
            return dict(station_id=sid,status='running' if alive else 'stopped' if not s['error'] and (p is None or p.exitcode==0) else 'failed',
                        pid=p.pid if alive else None,generation=s['generation'],error=s['error'],physical_dispatch=False)

    def _terminate(self,s):
        p=s['process']
        if p is not None:
            if p.is_alive():p.terminate()
            p.join(10)
            if p.is_alive():p.kill();p.join(5)
            p.close()
        if s['pipe'] is not None:s['pipe'].close()
        s['process']=None;s['pipe']=None

    def _receive(self,s):
        if not s['pipe'].poll(self.timeout):
            s['error']='Worker timeout; restart required';self._terminate(s);raise StationError(s['error'],503)
        try:r=s['pipe'].recv()
        except (EOFError,OSError):
            s['error']='Worker lost; restart required';self._terminate(s);raise StationError(s['error'],503)
        if not r['ok']:
            if r['status']==503:s['error']='Worker failed; restart required';self._terminate(s)
            raise StationError(r['detail'],r['status'])
        return r['result']

    def start(self,sid):
        s=self.slot(sid)
        with s['lock']:
            if s['process'] is not None and s['process'].is_alive():return self.request(sid,'state')
            self._terminate(s);s['error']=None;s['generation']=str(uuid.uuid4())
            folder=self.directory/sid;folder.mkdir(exist_ok=True)
            parent,child=self.context.Pipe();s['pipe']=parent
            p=self.context.Process(target=worker,args=(copy.deepcopy(self.configs[sid]),child,str(folder),s['generation']),name='gie-'+sid,daemon=True)
            s['process']=p;p.start();child.close()
            return self._receive(s)

    def request(self,sid,op,body=None):
        s=self.slot(sid)
        with s['lock']:
            p=s['process']
            if p is None or not p.is_alive():
                if p is not None:s['error']='Worker exited; restart required'
                raise StationError('Station not running; initialize or restart',503)
            try:s['pipe'].send(dict(op=op,body=body or {}))
            except (BrokenPipeError,OSError):
                s['error']='Worker lost; restart required';self._terminate(s);raise StationError(s['error'],503)
            return self._receive(s)

    def stop(self,sid):
        s=self.slot(sid)
        with s['lock']:
            if s['process'] is not None and s['process'].is_alive():
                try:s['pipe'].send({'op':'shutdown'});s['process'].join(5)
                except (BrokenPipeError,OSError):pass
            self._terminate(s);s['error']=None
            return self.health(sid)

    def restart(self,sid):
        s=self.slot(sid)
        with s['lock']:
            self.stop(sid);return self.start(sid)

    def close(self):
        if self.closed:return
        with self.registry_lock:
            for sid in list(self.slots):self.stop(sid)
            self.closed=True;self.owner.close()
