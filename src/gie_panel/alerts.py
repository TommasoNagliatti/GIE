"""Transactional local alert state + event history, no notification transport."""
from datetime import datetime,timezone
import json,sqlite3,threading,uuid
from pathlib import Path

def now():return datetime.now(timezone.utc).isoformat()
def key(code,equipment=None):return code+'|'+(equipment or '')

class Alerts:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False);self.lock=threading.RLock()
        self.db.executescript('''CREATE TABLE IF NOT EXISTS alerts(station TEXT, key TEXT, payload TEXT, PRIMARY KEY(station,key));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,station TEXT,event_id TEXT UNIQUE,payload TEXT);
        CREATE TABLE IF NOT EXISTS observations(station TEXT,source TEXT,PRIMARY KEY(station,source));''');self.db.commit()
    def close(self):self.db.close()
    def _save(self,sid,k,a,transition):
        a['revision']=a.get('revision',0)+1
        self.db.execute('INSERT OR REPLACE INTO alerts VALUES(?,?,?)',(sid,k,json.dumps(a,allow_nan=False)))
        event=dict(schema_version='1.0',event_id=a['alert_id']+':'+str(a['revision']),alert_id=a['alert_id'],station_id=sid,emitted_at=now(),transition=transition,alert=a,physical_dispatch=False,hardware_commands_sent=False)
        self.db.execute('INSERT INTO events(station,event_id,payload) VALUES(?,?,?)',(sid,event['event_id'],json.dumps(event,allow_nan=False)))
    def observe(self,sid,generation,occurred,source,conditions,domains):
        """Only observed domains can resolve. Polling/replay cannot add occurrences."""
        with self.lock,self.db:
            if self.db.execute('SELECT 1 FROM observations WHERE station=? AND source=?',(sid,source)).fetchone():return
            self.db.execute('INSERT INTO observations VALUES(?,?)',(sid,source))
            existing={k:json.loads(p) for k,p in self.db.execute('SELECT key,payload FROM alerts WHERE station=?',(sid,))}
            seen=set();detected=now()
            for c in conditions:
                k=key(c['code'],c.get('equipment_id'));seen.add(k);a=existing.get(k)
                if a is None:
                    a=dict(schema_version='1.0',alert_id=str(uuid.uuid4()),station_id=sid,code=c['code'],equipment_id=c.get('equipment_id'),first_seen=occurred,occurrence_count=1,acknowledged_at=None,resolved_at=None,status='OPEN',revision=0)
                    transition='CREATED'
                elif a['status']=='RESOLVED':
                    a.update(status='OPEN',occurrence_count=a['occurrence_count']+1,acknowledged_at=None,resolved_at=None);transition='REOPENED'
                else:transition='UPDATED'
                a.update(generation=generation,timestamp=occurred,detected_at=detected,last_seen=occurred,title=c['title'],description=c['description'],severity=c['severity'],domain=c['domain'],reason_codes=c.get('reason_codes',[c['code']]),numeric_context=c.get('numeric_context',{}),provenance={'origin':'SIMULATED','source_ref':source,'physical_dispatch':False},source_ref=source,clear_count=0)
                self._save(sid,k,a,transition)
            for k,a in existing.items():
                if k not in seen and a['status']!='RESOLVED' and a['domain'] in domains:
                    a['clear_count']=a.get('clear_count',0)+1
                    # Two consecutive valid observations for recovery; acknowledge never resolves.
                    if a['clear_count']>=2:
                        a.update(status='RESOLVED',resolved_at=occurred,detected_at=detected,generation=generation,timestamp=occurred,source_ref=source,provenance={'origin':'SIMULATED','source_ref':source,'physical_dispatch':False})
                        self._save(sid,k,a,'RESOLVED')
                    else:self.db.execute('UPDATE alerts SET payload=? WHERE station=? AND key=?',(json.dumps(a),sid,k))
    def list(self,sid,severity=None,status=None,equipment=None):
        with self.lock:
            values=[json.loads(p) for (p,) in self.db.execute('SELECT payload FROM alerts WHERE station=?',(sid,))]
        return sorted([a for a in values if (not severity or a['severity']==severity) and (not status or a['status']==status) and (not equipment or a['equipment_id']==equipment)],key=lambda a:a['detected_at'],reverse=True)
    def ack(self,sid,alert_id):
        with self.lock,self.db:
            row=next(((k,json.loads(p)) for k,p in self.db.execute('SELECT key,payload FROM alerts WHERE station=?',(sid,)) if json.loads(p)['alert_id']==alert_id),None)
            if row is None:raise KeyError('Unknown station alert')
            k,a=row
            if a['status']=='OPEN':a.update(status='ACKNOWLEDGED',acknowledged_at=now());self._save(sid,k,a,'ACKNOWLEDGED')
            return a
    def history(self,sid,after=0):
        with self.lock:return [dict(cursor=i,**json.loads(p)) for i,p in self.db.execute('SELECT seq,payload FROM events WHERE station=? AND seq>? ORDER BY seq LIMIT 500',(sid,after))]

def condition(code,title,domain='energy',severity='warning',equipment=None,**context):
    return dict(code=code,title=title,description='Condição observada na simulação; não representa diagnóstico físico ou causa interna do solver.',domain=domain,severity=severity,equipment_id=equipment,numeric_context=context)

def detect(result,equipment,current=None,active=()):
    n=result.get('numeric_state') or {};m=result.get('management') or {};v=result.get('visual_state') or {};extension=result.get('station_extension') or {}
    c=[];domains={'data','model'};active=set(active)
    if extension.get('training_state')=='BASELINE':c.append(condition('BASELINE_NO_HISTORY','Modelo BASELINE — sem histórico personalizado','model','info'))
    if extension.get('residential_ev_recall') is not None:c.append(condition('RESIDENTIAL_EV_LOW_RECALL','Previsão EV residencial com baixa confiabilidade','model','warning',recall=extension['residential_ev_recall']))
    for code in result.get('reason_codes',[]):
        if code.startswith('CURRENT_'):c.append(condition(code,'Dados atuais ausentes, antigos ou não confiáveis','data'))
    if not result.get('execution_allowed'):
        c.append(condition('EXECUTION_BLOCKED','Execução matemática bloqueada','data','error',status=result.get('status')))
        status=m.get('status','')
        if status in ('infeasible','solver_failed','blocked'):
            c.append(condition('MPC_INFEASIBLE' if status=='infeasible' else 'SOLVER_FAILED','MPC inviável' if status=='infeasible' else 'Solver bloqueado ou falhou','solver','critical',diagnostic=m.get('diagnostic')))
        # Missing current does not establish recovery from energy/solver failures.
    else:
        domains.update({'energy','solver','native'})
        unserved=n.get('ev_unserved_kw')
        if unserved is not None and unserved>(.05 if key('EV_POWER_LIMITED') in active else .1):c.append(condition('EV_POWER_LIMITED','Demanda EV não atendida',ev_unserved_kw=unserved))
        limit=equipment['import_kw'];gi=n.get('grid_import_kw')
        if limit and gi is not None and gi/limit>(.90 if key('GRID_NEAR_LIMIT') in active else .95):c.append(condition('GRID_NEAR_LIMIT','Importação próxima do limite',grid_import_kw=gi,limit_kw=limit))
        for b in equipment['batteries']:
            bid=b['battery_id'];decision=(m.get('first_decision') or {}).get('batteries',{}).get(bid,{})
            soc=decision.get('soc_after',n.get('battery_soc_after_pct')/100 if b.get('aggregate') and n.get('battery_soc_after_pct') is not None else None)
            if soc is not None and soc<=b['soc_min']+(.04 if key('BATTERY_SOC_MIN',bid) in active else .02):c.append(condition('BATTERY_SOC_MIN','SOC próximo ou no mínimo',equipment=bid,soc=soc,minimum=b['soc_min']))
        for e in equipment['evses']:
            eid=e['evse_id'];d=(n.get('evses') or {}).get(eid,{})
            state=(v.get('evses') or {}).get(eid,d.get('state'))
            if state in ('offline','fault'):c.append(condition('EVSE_FAULT' if state=='fault' else 'EVSE_OFFLINE','Carregador com falha' if state=='fault' else 'Carregador indisponível',equipment=eid))
            if state=='suspended':c.append(condition('EVSE_POWER_LIMITED','Carregador suspenso',equipment=eid))
        records=(result.get('forecasts') or {}).get('records') or []
        if records and records[0].get('origin')!='ESTIMATE':
            demand=n.get('ev_demand_kw');pred=records[0].get('potencia_solicitada_prevista_kw')
            if demand is not None and pred is not None and demand>pred+.1:c.append(condition('EV_DEMAND_ABOVE_FORECAST','Demanda atual acima da previsão',severity='info',demand_kw=demand,forecast_kw=pred))
        # Preserve native warnings/errors instead of recomputing their internals.
        existing={x['code'] for x in c}
        for message in result.get('messages',[]):
            if message.get('severity') in ('warning','error','critical'):
                for code in message.get('reason_codes',[]):
                    if code not in existing:
                        item=condition(code,message.get('title',code),'native',message['severity'],**message.get('numeric_context',{}));item['description']=message.get('text',item['description']);c.append(item);existing.add(code)
    if extension.get('operational_state')=='DEGRADED':c.append(condition('DEGRADED','Operação degradada','data'))
    if current is not None:
        building=current.get('building_kw');solar=current.get('solar_kw')
        if building is not None and solar is not None:
            domains.add('capacity')
            upper=equipment['import_kw']+solar+sum(b['discharge_kw'] for b in equipment['batteries'] if b.get('available',True) and current.get('battery_available',{}).get(b['battery_id'],True))
            if building>upper+1e-6:c.append(condition('MANDATORY_LOAD_ABOVE_CAPACITY','Carga obrigatória acima da capacidade disponível','capacity','critical',building_kw=building,supply_upper_bound_kw=upper))
        for bid,available in current.get('battery_available',{}).items():
            if bid not in {b['battery_id'] for b in equipment['batteries']}:continue
            domain='battery_availability:'+bid;domains.add(domain)
            if not available:c.append(condition('BATTERY_UNAVAILABLE','Bateria indisponível',domain,equipment=bid))
        for iid,available in current.get('inverter_available',{}).items():
            if iid not in {i['inverter_id'] for i in equipment.get('inverters',[])}:continue
            domain='inverter_availability:'+iid;domains.add(domain)
            if not available:c.append(condition('INVERTER_UNAVAILABLE','Inversor indisponível',domain,equipment=iid))
    return c,domains
