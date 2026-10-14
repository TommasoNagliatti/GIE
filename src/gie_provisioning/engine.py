"""No CSV/model dependency. Baselines are estimates; current is never fabricated."""
from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd
from gie_energy_v3.mpc import optimize
from gie_energy_v3.balancer import allocate
from gie_energy_v3.guard import verify
from gie_energy_v3.state import SimulatedState
from .contracts import Provision,Sample,ModelState

STEP=pd.Timedelta(minutes=15)
def timestamp(value,timezone,aligned=False):
    t=pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:raise ValueError('Explicit timestamp offset required')
    t=t.tz_convert(timezone)
    if aligned and (t.minute%15 or t.second or t.microsecond or t.nanosecond):raise ValueError('15-minute alignment required')
    return t

class BaselineEngine:
    def __init__(self,config):
        self.config=config;self.technical=Provision.model_validate(config['technical'])
        self.energy_config=self.technical.energy_config();self.simulation=SimulatedState(self.energy_config,Path.cwd()/'energy_state_v3.json')
        self.last_issue=self.simulation.last_issue;self.cache={};self.history=[]
        self.model_identity=dict(station_id=self.technical.station_id,state='BASELINE',version='baseline-v1',personalized=False,artifact_path=None)
        self.model_state=ModelState(station_id=self.technical.station_id).model_dump()
    def energy_state_view(self):return self.simulation.view()
    def run_cycle(self,issue_time,current=None,mode='NORMAL'):
        t=timestamp(issue_time,self.technical.timezone,True)
        if self.last_issue is not None and t!=self.last_issue+STEP:raise ValueError('Next contiguous interval required; replay/gaps rejected')
        c=deepcopy(self.energy_config);reason=None;sample=None
        if current is None:reason='CURRENT_MISSING'
        else:
            sample=Sample.model_validate(current)
            if sample.station_id!=c.station_id:raise ValueError('Sample station mismatch')
            observed=timestamp(sample.observed_at,self.technical.timezone);available=timestamp(sample.available_at,self.technical.timezone)
            if available<observed or available>t or observed>t or t-observed>pd.Timedelta(minutes=5):reason='CURRENT_STALE_OR_FUTURE'
            if sample.quality!='TRUSTED':reason='CURRENT_UNTRUSTED'
            if set(sample.battery_available)-{b.battery_id for b in c.batteries} or set(sample.inverter_available)-{i.inverter_id for i in c.inverters}:raise ValueError('Unknown availability identity')
            for b in c.batteries:b.available=b.available and sample.battery_available.get(b.battery_id,True)
            for i in c.inverters:i.available=i.available and sample.inverter_available.get(i.inverter_id,True)
            if not sample.grid_available:c.import_kw=c.export_kw=0.
            if sample.solar_kw>sum(i.pv_dc_kwp for i in c.inverters):raise ValueError('Solar outside configured envelope')
            requests={d.evse_id:d.model_dump(exclude_none=True) for d in sample.demands}
            if len(requests)!=len(sample.demands) or set(requests)!={e.evse_id for e in c.evses}:raise ValueError('Exact EVSE identities required')
            for e in c.evses:
                d=requests[e.evse_id]
                if d['requested_kw']>e.max_kw or (not d['connected'] and d['requested_kw']>0):raise ValueError('Invalid EVSE demand')
        trusted=sample is not None and reason is None
        # Technical envelope is not observed building demand. No guaranteed future PV.
        bbase=self.technical.baseline_building_kw
        if trusted:bbase=max(sample.building_kw,bbase or 0.)
        forecast=[dict(timestamp=(t+h*STEP).isoformat(),building_kw=bbase,
            potencia_solicitada_prevista_kw=sum(e.max_kw for e in c.evses if e.available),
            solar_previsto_kw=0.,origin='ESTIMATE',method='technical_envelope_v1',is_measurement=False) for h in range(48)]
        numeric={k:None for k in ['building_kw','solar_kw','ev_demand_kw','battery_soc_pct','battery_soc_after_pct','battery_charge_kw','battery_discharge_kw','grid_import_kw','grid_export_kw','ev_served_kw','ev_unserved_kw','ev_block_limit_kw','energy_balance_error_kw']}
        numeric['evse_setpoints_kw']=[None]*len(c.evses)
        visual=dict(valid=False,commands_valid=False,grid_flow='unknown',battery_flow='unknown',solar='unknown',evses={e.evse_id:'unknown' for e in c.evses})
        for j in range(1,max(4,len(c.evses))+1):
            visual[f'evse_{j}_active']=None;visual[f'evse_{j}_fault']=None
        for key in ['solar_active','building_active','grid_importing','grid_exporting','battery_charging','battery_discharging']:visual[key]=None
        result=dict(output_version='1.0',timestamp=t.isoformat(),decision_time=t.isoformat(),mode=mode,profile='dynamic_baseline_v1',status='degraded',execution_allowed=False,
            physical_dispatch=False,hardware_commands_sent=False,numeric_state=numeric,visual_state=visual,
            forecasts=dict(records=forecast,steps=48,interval_minutes=15,timezone=self.technical.timezone,origin='ESTIMATE',personalized=False),
            management=dict(execution_allowed=False,physical_dispatch=False),load_balancer=dict(available=False,setpoints_kw={e.evse_id:None for e in c.evses}),
            station_extension=dict(schema_version='1.0',station_id=c.station_id,training_state='BASELINE',operational_state='DEGRADED',model_state=self.model_state,
                simulation_state=self.simulation.view(),current_trusted=trusted,energy_version='3.0',policy=c.policy),
            provenance=dict(origin='SIMULATED',station_id=c.station_id,input_source='explicit simulated current only',forecast_origin='ESTIMATE',history_records=len(self.history)),
            presentation_metadata=dict(hardware_commands_sent=False,setpoints_are_limits=True,llm_calls=0))
        if trusted:
            building=np.full(48,bbase);building[0]=sample.building_kw
            pv=np.zeros((48,len(c.inverters)));weights=np.array([i.pv_dc_kwp for i in c.inverters])
            if weights.sum():pv[0]=sample.solar_kw*weights/weights.sum()
            demand=np.tile([e.max_kw if e.available else 0. for e in c.evses],(48,1))
            for j,e in enumerate(c.evses):
                d=requests[e.evse_id]
                if not d['available'] or not e.available:demand[:,j]=0.
                demand[0,j]=min(d['requested_kw'],d.get('vehicle_max_kw',e.max_kw)) if d['connected'] and d['available'] and e.available else 0.
            initial=dict(self.simulation.energy);management=optimize(c,initial,building,pv,demand);result['management']=management
            if management['execution_allowed']:
                first=management['first_decision'];allocation=allocate(c.evses,requests,max(0.,first['ev_served_kw']),c.circuits,self.simulation.cycles)
                if abs(allocation['allocated_kw']-first['ev_served_kw'])>2e-5:raise ValueError('Allocator changed feasible total')
                first['evse_setpoints_kw']=allocation['setpoints_kw'];first['ev_served_kw']=allocation['allocated_kw']
                management['verification']=verify(c,initial,building,pv,demand,management['plan'])
                self.simulation.commit(t,first);self.last_issue=t
                result.update(status='optimal_simulated',execution_allowed=True,load_balancer=dict(available=True,**allocation))
                numeric.update({k:first[k] for k in ['building_kw','grid_import_kw','grid_export_kw','ev_served_kw']})
                numeric.update(solar_kw=sample.solar_kw,ev_demand_kw=sum(d['requested_kw'] for d in requests.values()),evse_setpoints_kw=list(allocation['setpoints_kw'].values()),evses=requests,
                    battery_charge_kw=sum(b['charge_kw'] for b in first['batteries'].values()),battery_discharge_kw=sum(b['discharge_kw'] for b in first['batteries'].values()),
                    ev_block_limit_kw=first['ev_served_kw'],energy_balance_error_kw=first['balance_error_kw'])
                numeric['ev_unserved_kw']=max(0.,numeric['ev_demand_kw']-first['ev_served_kw'])
                capacity=sum(b.capacity_kwh for b in c.batteries)
                if capacity:numeric.update(battery_soc_pct=100*sum(initial.values())/capacity,battery_soc_after_pct=100*sum(self.simulation.energy.values())/capacity)
                visual.update(valid=True,solar_active=sample.solar_kw>1e-5,building_active=sample.building_kw>1e-5,grid_importing=first['grid_import_kw']>1e-5,grid_exporting=first['grid_export_kw']>1e-5,battery_charging=numeric['battery_charge_kw']>1e-5,battery_discharging=numeric['battery_discharge_kw']>1e-5)
                visual['solar']='active' if visual['solar_active'] else 'inactive'
                visual['grid_flow']='importing' if visual['grid_importing'] else 'exporting' if visual['grid_exporting'] else 'idle'
                visual['battery_flow']='charging' if visual['battery_charging'] else 'discharging' if visual['battery_discharging'] else 'idle'
                for j,e in enumerate(c.evses,1):
                    d=requests[e.evse_id];power=allocation['setpoints_kw'][e.evse_id]
                    visual[f'evse_{j}_active']=power>1e-5;visual[f'evse_{j}_fault']=not d['available']
                    visual['evses'][e.evse_id]='offline' if not d['available'] else 'disconnected' if not d['connected'] else 'charging' if power>1e-5 else 'suspended'
                result['station_extension'].update(operational_state='BASELINE',simulation_state=self.simulation.view(),battery_decisions=first['batteries'])
                self.history.append(dict(timestamp=t.isoformat(),origin='SIMULATED',building_kw=sample.building_kw));self.history=self.history[-100:]
                reason='BASELINE_SIMULATED_ONLY'
            else:reason='MPC_'+management['status'].upper()
        message=dict(code=reason,severity='info' if result['execution_allowed'] else 'warning',text='Baseline estimates; no physical dispatch. '+str(reason),reason_codes=[reason])
        result.update(primary_message=message,messages=[message],events=[dict(code=reason,origin='SIMULATED')],reason_codes=[reason],maquette_state=deepcopy(visual))
        self.cache=dict(issue_time=t.isoformat(),forecast_rows=48,origin='ESTIMATE')
        return result
