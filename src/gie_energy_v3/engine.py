"""Versioned adapter; original commercial engine and learned models stay intact."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pandas as pd
from gie_multistation.engines import ForecastEngine,local_time,STEP
from gie_multistation.registry import ROOT
from .config import from_manifest
from .mpc import optimize
from .guard import verify
from .balancer import allocate
from .state import SimulatedState

class EnergyEngine(ForecastEngine):
    def __init__(self,config,state_path=None):
        super().__init__(config)
        self.energy_config=from_manifest(json.loads((ROOT/config['profile_path']).read_text(encoding='utf-8')))
        self.simulation=SimulatedState(self.energy_config,state_path or Path.cwd()/'energy_state_v3.json')
        self.last_issue=self.simulation.last_issue
    def energy_state_view(self):return self.simulation.view()
    def run_cycle(self,issue_time,current=None,mode='NORMAL'):
        t=local_time(issue_time)
        if self.last_issue is not None and t!=self.last_issue+STEP:raise ValueError('Energy simulation requires next contiguous 15-minute interval; replay/gaps rejected')
        simple=deepcopy(current)
        if simple:
            for d in simple['demands']:
                d.pop('available',None);d.pop('vehicle_max_kw',None)
        out=super().run_cycle(t,simple,mode)
        c=self.energy_config;records=out['forecasts']['records'];n=out['numeric_state'];i=int(np.flatnonzero(self.times==t)[0])
        requests={d['evse_id']:deepcopy(d) for d in (current['demands'] if current else out['station_extension']['evses'])}
        if current is None:
            for j,e in enumerate(c.evses):
                requests[e.evse_id]['available']=bool(self.ev.iloc[i][f'evse_{j+1:02d}_available_fraction']>0)
        demands=np.zeros((48,len(c.evses)));caps=np.array([e.max_kw for e in c.evses]);totalcap=caps.sum()
        learned=np.array([r['potencia_solicitada_prevista_kw'] for r in records])
        if c.station_id=='DEMO_CASA_001':learned=np.maximum(learned,sum(d['requested_kw'] for d in requests.values() if d['connected']))
        if totalcap:demands[:]=learned[:,None]*(caps/totalcap)[None,:]
        for j,e in enumerate(c.evses):
            d=requests[e.evse_id];cap=min(e.max_kw,d.get('vehicle_max_kw',e.max_kw))
            demands[0,j]=min(d['requested_kw'],cap) if d['connected'] and d.get('available',True) and e.available else 0.
            if not d.get('available',True):demands[:,j]=0.
        building=np.array([r['building_kw'] for r in records]);building[0]=n['building_kw']
        # Causal previous-day PV baseline, never future TMY. Current first step is a separate fixture.
        day_positions=[int(np.flatnonzero(self.times==t+STEP*h-pd.Timedelta(days=1))[0]) for h in range(48)]
        solar=np.array([float(self.energy.iloc[k].pv_generation_ac_kw) for k in day_positions]);solar[0]=n['solar_kw']
        weights=np.array([v.pv_dc_kwp for v in c.inverters]);pv=solar[:,None]*(weights/weights.sum())[None,:] if weights.sum() else np.zeros((48,len(weights)))
        initial=dict(self.simulation.energy)
        result=optimize(c,initial,building,pv,demands)
        out['station_extension'].update(dispatch_available=True,load_balancer_available=True,unavailable_reason=None,
            energy_version='3.0',policy=c.policy,physical_dispatch=False,simulation_state=self.simulation.view(),
            solar_forecast_source='previous-day PV baseline; current simulated measurement at step 0',
            forecast_scenarios='future EV distributed by installed capacities; current EV authoritative, residential current-demand envelope; future availability assumed unchanged')
        out['provenance']['energy_state']='persistent individual SIMULATED energy, not meter readings'
        out['management']=result
        if not result['execution_allowed']:
            out['status']=result['status'];out['reason_codes']=['ENERGY_V3_BLOCKED'];out['events']=[{'code':'ENERGY_V3_BLOCKED','diagnostic':result.get('diagnostic'),'origin':'SIMULATED'}]
            out['messages']=[{'code':'ENERGY_V3_BLOCKED','severity':'error','text':result.get('diagnostic','Solver blocked'),'reason_codes':['ENERGY_V3_BLOCKED']}];out['primary_message']=out['messages'][0]
            return out
        first=result['first_decision']
        allocation=allocate(c.evses,requests,max(0.,first['ev_served_kw']),c.circuits,self.simulation.cycles)
        if abs(allocation['allocated_kw']-first['ev_served_kw'])>2e-5:raise ValueError('Balancer changed MPC total; no decision committed')
        first['evse_setpoints_kw']=allocation['setpoints_kw'];first['ev_served_kw']=allocation['allocated_kw']
        result['verification']=verify(c,initial,building,pv,demands,result['plan'])
        self.simulation.commit(t,first);self.last_issue=t
        out['station_extension']['simulation_state']=self.simulation.view()
        out['station_extension']['battery_decisions']=first['batteries']
        out['station_extension']['solar_available_kw']=first['solar_available_kw'];out['station_extension']['solar_used_kw']=first['solar_used_kw'];out['station_extension']['solar_curtailed_kw']=first['solar_curtailed_kw']
        out['status']='optimal_simulated';out['execution_allowed']=True
        n.update(grid_import_kw=first['grid_import_kw'],grid_export_kw=first['grid_export_kw'],
            battery_charge_kw=sum(b['charge_kw'] for b in first['batteries'].values()),battery_discharge_kw=sum(b['discharge_kw'] for b in first['batteries'].values()),
            ev_served_kw=first['ev_served_kw'],ev_block_limit_kw=first['ev_served_kw'],ev_unserved_kw=max(0.,n['ev_demand_kw']-first['ev_served_kw']),energy_balance_error_kw=first['balance_error_kw'],evse_setpoints_kw=list(first['evse_setpoints_kw'].values()))
        capacity=sum(b.capacity_kwh for b in c.batteries)
        n['battery_soc_pct']=100*sum(initial.values())/capacity if capacity else None
        n['battery_soc_after_pct']=100*sum(self.simulation.energy.values())/capacity if capacity else None
        visual=out['visual_state'];visual.update(valid=True,commands_valid=False,grid_importing=first['grid_import_kw']>1e-5,grid_exporting=first['grid_export_kw']>1e-5,
            battery_charging=n['battery_charge_kw']>1e-5,battery_discharging=n['battery_discharge_kw']>1e-5)
        visual['grid_flow']='importing' if visual['grid_importing'] else 'exporting' if visual['grid_exporting'] else 'idle'
        visual['battery_flow']='charging' if visual['battery_charging'] else 'discharging' if visual['battery_discharging'] else 'idle'
        for j,e in enumerate(c.evses,1):
            d=requests[e.evse_id];power=first['evse_setpoints_kw'][e.evse_id]
            visual[f'evse_{j}_active']=power>1e-5;visual[f'evse_{j}_fault']=not d.get('available',True)
            visual['evses'][e.evse_id]='offline' if not d.get('available',True) else 'disconnected' if not d['connected'] else 'charging' if power>1e-5 else 'suspended'
        out['maquette_state']=deepcopy(visual);out['load_balancer']=dict(available=True,**allocation)
        message={'code':'SIMULATED_DECISION','severity':'info','text':'Energy V3 verified; first decision applied only to simulated state.','reason_codes':['SIMULATED_ONLY']}
        out['messages']=[message];out['primary_message']=message;out['reason_codes']=['SIMULATED_ONLY']
        out['events']=[e for e in out['events'] if e['code']=='RESIDENTIAL_EV_LOW_RECALL']
        out['events'].append({'code':'SIMULATED_STATE_COMMITTED','origin':'SIMULATED','hardware_commands_sent':False})
        return out
