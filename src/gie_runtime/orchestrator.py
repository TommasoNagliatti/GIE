"""One 15-minute GIE cycle. No optimizer, predictor or allocator is reimplemented."""
from dataclasses import replace,asdict
import json
import math
from time import perf_counter
import pandas as pd
from .models import json_safe
from .health import initial_health,timed
from .adapters import history_until,aligned_forecasts
from integracoes.weather.models import horizon,local_time,STEP
from motor_gerenciamento.config import Config
from motor_gerenciamento.state import State,Measurements
from motor_gerenciamento.run import run_control
from motor_gerenciamento.dispatch import apply_first
from motor_gerenciamento.events import from_decision
from load_balancer import run_balancer,Config as LBConfig

def run_gie_cycle(decision_time,history,current,components,config=None,balancer_state=None,balancer_config=None):
    started=perf_counter();health=initial_health();c=config or Config();lbc=balancer_config or LBConfig()
    out=dict(gie_version='1.0',motor3_version='1.1',decision_time=str(decision_time),status='blocked',
             current_state=json_safe(current),forecasts=None,management={'execution_allowed':False},
             load_balancer=None,flows=None,events=[],health=health,history_provenance=history.provenance)
    def validate():
        c.validate();ix=horizon(decision_time);t=ix[0].tz_localize(None)
        if local_time(current.timestamp).tz_localize(None)!=t:raise ValueError('Current telemetry timestamp differs from decision time.')
        for v in (current.building_kw,current.ev_demand_kw,current.solar_kw,current.battery_soc_pct,current.previous_charge_kw,current.previous_discharge_kw):
            if not math.isfinite(v) or v<0:raise ValueError('Invalid current telemetry.')
        if not c.soc_min_pct<=current.battery_soc_pct<=c.soc_max_pct or current.solar_kw>c.pv_ac_max_kw:raise ValueError('Telemetry outside physical limits.')
        ds=[replace(e,connected_since=None if e.connected_since is None else local_time(e.connected_since).tz_localize(None).to_pydatetime()) for e in current.evses]
        return t,ds
    try:
        t,evses=timed(health,'validation',validate);out['decision_time']=str(t)
        origin=t-STEP
        a=timed(health,'motor1',lambda:components.motor1.predict(history_until(history.building,origin),origin))
        b=timed(health,'motor2',lambda:components.motor2.predict(history_until(history.ev,origin),origin))
        solar=timed(health,'solar',lambda:components.solar.forecast(t))
        health['solar'].update(source=solar.source,stale=solar.stale,diagnostics=solar.metadata.get('diagnostics',[]))
        if solar.stale or solar.source in ('cache','fallback'):
            health['solar']['status']='degraded'
            out['events'].append(dict(code='SOLAR_FORECAST_'+solar.source.upper(),severity='warning',timestamp=str(t),context=health['solar'].copy()))
        series,records=timed(health,'alignment',lambda:aligned_forecasts(a,b,solar,t))
        out['forecasts']=dict(records=records,steps=48,interval_minutes=15,timezone='America/Sao_Paulo',solar_metadata=solar.metadata,solar_source=solar.source,solar_stale=solar.stale)
        # Validate four EVSEs and ask the existing allocator for their envelope.
        capacity,_=timed(health,'load_balancer',lambda:run_balancer(c.ev_max_kw,evses,t,balancer_state,lbc))
        effective_ev=min(current.ev_demand_kw,capacity['allocated_total_kw'])
        state=State(current.battery_soc_pct,current.previous_charge_kw,current.previous_discharge_kw)
        management=timed(health,'motor3',lambda:run_control(a,b,series,state=state,config=c,
            execution_measurements=Measurements(t,current.building_kw,effective_ev,current.solar_kw),solver=components.solver))
        health['motor3'].update(solver_status=management['solver_status'],fallback_used=management['fallback_used'],reason=management.get('fallback_reason'))
        if not management['execution_allowed']:
            out['events'].extend(management['events']);raise RuntimeError('Motor 3 cannot provide a safe execution.')
        if management['fallback_used']:health['motor3']['status']='degraded'
        allocated,next_state=timed(health,'load_balancer',lambda:run_balancer(management['ev_block_limit_kw'],evses,t,balancer_state,lbc))
        # Hardware minima/faults can reduce feasible delivery. Re-project only
        # the uncommitted current action with the existing Motor 3 guard.
        if allocated['allocated_total_kw']+c.tolerance < management['first_decision']['ev_served_kw']:
            stage=perf_counter()
            effective_ev=min(effective_ev,allocated['allocated_total_kw'])
            decision=dict(management['planned_first_decision'],ev_block_limit_kw=allocated['allocated_total_kw'])
            executed=apply_first(decision,state,current.building_kw,min(effective_ev,allocated['allocated_total_kw']),current.solar_kw,c)
            management['first_decision']=executed
            for key in ('battery_charge_kw','battery_discharge_kw','ev_block_limit_kw','grid_import_plan_kw','grid_export_plan_kw','battery_soc_before_pct','battery_soc_after_pct'):management[key]=executed[key]
            management['events']=from_decision(executed,state,c,management['fallback_used'])
            health['motor3']['elapsed_ms']+=(perf_counter()-stage)*1000
            allocated,next_state=timed(health,'load_balancer',lambda:run_balancer(management['ev_block_limit_kw'],evses,t,balancer_state,lbc))
        row=management['first_decision']
        assert allocated['ev_block_limit_kw']==management['ev_block_limit_kw']
        assert row['ev_served_kw']<=allocated['allocated_total_kw']+c.tolerance
        assert allocated['allocated_total_kw']<=management['ev_block_limit_kw']+c.tolerance
        balance=current.solar_kw+row['grid_import_plan_kw']+row['battery_discharge_kw']-current.building_kw-row['ev_served_kw']-row['battery_charge_kw']-row['grid_export_plan_kw']
        assert abs(balance)<c.tolerance
        assert row['battery_charge_kw']<=max(0,current.solar_kw-current.building_kw-effective_ev)+c.tolerance
        assert abs(row['flows'].get('grid_to_battery_kw',0))<c.tolerance
        out['events'].extend(management['events']);out['events'].extend(allocated['events'])
        faulted=[e.evse_id for e in evses if e.state in ('fault','offline')]
        if faulted:health['load_balancer'].update(status='degraded',unavailable_evses=faulted)
        unavailable=max(0,current.ev_demand_kw-effective_ev)
        if unavailable>c.tolerance:
            health['load_balancer']['status']='degraded'
            out['events'].append(dict(code='EVSE_CAPACITY_LIMITED',severity='warning',timestamp=str(t),context={'unavailable_kw':unavailable}))
        out['management']={k:v for k,v in management.items() if k!='llm_payload'}
        out['management'].update(policy='solar_only_battery_charging',physical_config=asdict(c),
            current_ev_demand_kw=current.ev_demand_kw,dispatchable_ev_demand_kw=effective_ev,
            current_ev_unserved_total_kw=current.ev_demand_kw-row['ev_served_kw'],applied_step=0,
            power_balance_error_kw=abs(balance),only_first_step_applied=True,
            flow_basis='Current measured/dispatchable demand; EVSE setpoints are upper limits, not metered consumption.')
        out['flows']=row['flows'];out['load_balancer']=allocated
        out['load_balancer']['next_state']=asdict(next_state)
        out['status']='degraded' if any(h['status']=='degraded' for h in health.values()) else 'ok'
    except Exception as e:
        health['cycle_error']=dict(status='error',error_type=type(e).__name__,error=str(e))
        if health['motor3']['status']=='ok' and out['management']['execution_allowed'] is False and health['motor3'].get('solver_status')=='physically_infeasible':health['motor3']['status']='error'
        out['status']='blocked';out['management']={'execution_allowed':False}
        out['flows']=None;out['load_balancer']=None
        out['events'].append(dict(code='GIE_CYCLE_BLOCKED',severity='critical',timestamp=str(decision_time),context={'type':type(e).__name__,'reason':str(e)}))
    health['total_elapsed_ms']=(perf_counter()-started)*1000
    answer=json_safe(out)
    json.dumps(answer,allow_nan=False)
    return answer
