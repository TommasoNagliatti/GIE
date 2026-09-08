"""Pure deterministic evidence extraction. Never changes or explains solver internals."""
from copy import deepcopy
from datetime import datetime
import hashlib,json,math

EPS=1e-6

def component_for(code):
    if code.startswith('EVSE_') or code=='EV_BLOCK_FULLY_ALLOCATED':return 'load_balancer'
    if code.startswith('SOLAR_FORECAST'):return 'solar'
    if code.startswith('GIE_'):return 'runtime'
    return 'motor3'

def close(a,b):
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return abs(a-b)<=EPS
    return a==b

def build_trace(cycle,previous=None,include_llm_context=True):
    c=deepcopy(cycle);previous=deepcopy(previous) if previous else None
    ts=c['decision_time'];cur=c.get('current_state') or {};mg=c.get('management') or {};lb=c.get('load_balancer') or {}
    if previous and datetime.fromisoformat(previous['timestamp'])>datetime.fromisoformat(ts):raise ValueError('Previous trace cannot be newer than current cycle.')
    config=mg.get('physical_config') or {};row=mg.get('first_decision') or {}
    forecast=((c.get('forecasts') or {}).get('records') or [{}])[0]
    pv=cur.get('solar_kw');building=cur.get('building_kw');ev=cur.get('ev_demand_kw')
    peak=max((r.get('building_kw',0)+r.get('potencia_solicitada_prevista_kw',0)-r.get('solar_previsto_kw',0) for r in (c.get('forecasts') or {}).get('records',[])),default=None)
    ctx=dict(building_kw=building,ev_demand_kw=ev,solar_kw=pv,soc_before_pct=cur.get('battery_soc_pct'),
        soc_after_pct=mg.get('battery_soc_after_pct'),reserve_pct=config.get('reserve_pct'),grid_target_kw=config.get('grid_target_kw'),
        grid_max_kw=config.get('grid_import_max_kw'),ev_block_limit_kw=mg.get('ev_block_limit_kw'),
        ev_served_kw=row.get('ev_served_kw'),ev_unserved_kw=mg.get('current_ev_unserved_total_kw',row.get('ev_unserved_kw')),
        building_forecast_kw=forecast.get('building_kw'),ev_forecast_kw=forecast.get('potencia_solicitada_prevista_kw'),
        ev_q90_kw=forecast.get('potencia_solicitada_alta_kw'),future_net_peak_kw=peak)
    prior={d['action']:d['new_value'] for d in previous.get('decisions',[])} if previous else {}
    decisions=[]
    def decision(action,value,component,reasons,context,baseline=None,baseline_source=None):
        old=prior.get(action,baseline);known=action in prior or baseline_source is not None
        changed=known and not close(old,value)
        decisions.append(dict(timestamp=ts,action=action,component=component,previous_value=old,new_value=value,
            changed=changed,previous_known=known,baseline_source='previous_trace' if action in prior else baseline_source,
            reason_codes=list(dict.fromkeys(reasons or (['SETPOINT_UNCHANGED'] if known and not changed else ['DECISION_OBSERVED']))),context=context))
    allowed=bool(mg.get('execution_allowed',False))
    decision('execution_allowed',allowed,'runtime',['EXECUTION_ALLOWED' if allowed else 'EXECUTION_BLOCKED'],{'status':c.get('status')})
    if allowed:
        surplus=None if None in (pv,building,ev) else max(0,pv-building-ev)
        net=None if None in (pv,building,ev) else building+ev-pv
        charge=mg['battery_charge_kw'];discharge=mg['battery_discharge_kw'];reserve=ctx['reserve_pct'];target=ctx['grid_target_kw']
        charge_codes=['SOLAR_SURPLUS'] if charge>EPS and surplus is not None and surplus>EPS else []
        if charge>EPS and peak is not None and target is not None and peak>target:charge_codes.append('FUTURE_PEAK_PRESENT')
        discharge_codes=[]
        if discharge>EPS:
            discharge_codes.append('GRID_TARGET_PROTECTION' if target is not None and net is not None and net>target else 'BATTERY_SUPPLY_TO_LOAD')
            if ctx['grid_max_kw'] is not None and net is not None and net>ctx['grid_max_kw']:discharge_codes.append('GRID_PHYSICAL_LIMIT_PROTECTION')
        if discharge<=EPS and reserve is not None and ctx['soc_before_pct'] is not None and ctx['soc_before_pct']<=reserve+EPS:discharge_codes.append('BATTERY_RESERVE_PROTECTION')
        decision('battery_charge_kw',charge,'motor3',charge_codes,{**ctx,'actual_solar_surplus_kw':surplus},cur.get('previous_charge_kw'), 'current_state' if 'previous_charge_kw' in cur else None)
        decision('battery_discharge_kw',discharge,'motor3',discharge_codes,{**ctx,'net_load_before_battery_kw':net},cur.get('previous_discharge_kw'),'current_state' if 'previous_discharge_kw' in cur else None)
        codes=[]
        if ctx['ev_unserved_kw'] is not None and ctx['ev_unserved_kw']>EPS:codes.append('EV_POWER_LIMITED')
        if ev is not None and ctx['ev_forecast_kw'] is not None and ev>ctx['ev_forecast_kw']+EPS:codes.append('EV_DEMAND_ABOVE_FORECAST')
        if row.get('ev_block_limit_relaxed'):codes.append('EV_BLOCK_LIMIT_RELAXED')
        decision('ev_block_limit_kw',mg['ev_block_limit_kw'],'motor3',codes,ctx)
        imported=mg['grid_import_plan_kw'];exported=mg['grid_export_plan_kw']
        reasons=['GRID_DEFICIT_SUPPLY'] if imported>EPS else []
        if target is not None and imported>target+EPS:reasons.append('GRID_TARGET_EXCEEDED')
        if target is not None and building is not None and building>target:reasons.append('HIGH_BUILDING_DEMAND')
        decision('grid_import_plan_kw',imported,'motor3',reasons,ctx)
        decision('grid_export_plan_kw',exported,'motor3',['GRID_EXPORT_SURPLUS'] if exported>EPS else [],ctx)
        for i in range(1,5):
            device=lb.get(f'EVSE{i}',{});value=lb.get(f'evse_{i}_kw')
            if value is None:continue
            codes=['EVSE_FAULT'] if device.get('state')=='fault' else []
            if device.get('requested_kw',0)>value+EPS:codes.append('EVSE_POWER_LIMITED')
            if not device.get('connected',True):codes.append('EVSE_DISCONNECTED')
            decision(f'evse_{i}_kw',value,'load_balancer',codes,dict(evse_id=f'EVSE{i}',state=device.get('state'),requested_kw=device.get('requested_kw'),block_kw=lb.get('ev_block_limit_kw')))
    events=[]
    for e in c.get('events',[]):
        context=deepcopy(e.get('context') or {})
        old=e.get('previous_value');new=e.get('new_value')
        if e['code']=='EVSE_FAULT':
            identity=e.get('evse_id',context.get('evse_id'))
            new=next((v.get('state') for v in cur.get('evses',[]) if v.get('evse_id')==identity),'fault')
            old=next((v.get('state') for v in (previous or {}).get('current_state',{}).get('evses',[]) if v.get('evse_id')==identity),None)
        if e.get('evse_id') is not None:context['evse_id']=e['evse_id']
        events.append(dict(timestamp=e.get('timestamp',ts),code=e['code'],severity=e.get('severity','info'),component=e.get('component',component_for(e['code'])),
            previous_value=old,new_value=new,reason_codes=e.get('reason_codes',[e['code']]),context=context))
    # Measured-vs-forecast comparison is evidence, never proof of control causation.
    for label,actual,pred in [('BUILDING',building,ctx['building_forecast_kw']),('EV',ev,ctx['ev_forecast_kw'])]:
        if actual is not None and pred is not None and pred>actual+EPS:
            code=label+'_FORECAST_ABOVE_REALIZED'
            events.append(dict(timestamp=ts,code=code,severity='info',component='motor1' if label=='BUILDING' else 'motor2',
                previous_value=None,new_value=actual,reason_codes=['FORECAST_ABOVE_REALIZED'],context={'forecast_kw':pred,'realized_kw':actual,'difference_kw':pred-actual}))
    if pv is not None and pv<=EPS:
        events.append(dict(timestamp=ts,code='LOW_SOLAR_GENERATION',severity='info',component='telemetry',previous_value=None,new_value=pv,reason_codes=['LOW_SOLAR_GENERATION'],context={'measured_solar_kw':pv}))
    trace=dict(trace_version='1.0',timestamp=ts,status=c.get('status'),current_state=cur,decisions=decisions,
        changes=[deepcopy(d) for d in decisions if d['changed']],flows=deepcopy(c.get('flows')),events=events,health=deepcopy(c.get('health')),
        explanation_basis='Observed numerical conditions and native events; not solver sensitivity or causal attribution.',
        flow_basis=mg.get('flow_basis','Unavailable: execution may be blocked.'))
    trace['trace_id']=hashlib.sha256(json.dumps({'timestamp':ts,'decisions':decisions,'events':events},sort_keys=True,allow_nan=False).encode()).hexdigest()[:24]
    if include_llm_context:
        important=[d for d in decisions if d['changed'] or any(code not in ('SETPOINT_UNCHANGED','DECISION_OBSERVED','EXECUTION_ALLOWED') for code in d['reason_codes'])]
        trace['llm_context']=dict(version='1.0',timestamp=ts,status=c.get('status'),api_called=False,
            evidence_only=True,decisions=[{k:d[k] for k in ('action','previous_value','new_value','component','reason_codes')} for d in important[:10]],
            event_codes=list(dict.fromkeys(e['code'] for e in sorted(events,key=lambda e:{'critical':0,'error':1,'warning':2,'info':3}.get(e['severity'],4))))[:12],numbers=ctx,
            degraded_components=[k for k,v in (c.get('health') or {}).items() if isinstance(v,dict) and v.get('status') in ('degraded','error')])
    json.dumps(trace,allow_nan=False)
    return trace
