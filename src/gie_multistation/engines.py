"""Worker-owned engines. No commands, network calls, or commercial authority."""
import copy
import hashlib
import json
from types import SimpleNamespace
import numpy as np
import pandas as pd
from gie_control import GIEControl, GIEEngine
from gie_control.profile import load_profile
from gie_control.scenarios import LocalSolar
from gie_runtime import Components, History, CurrentState
from gie_runtime.models import json_safe
from load_balancer import EVSEState
from load_balancer.state import BalancerState
from .registry import ROOT, digest

STEP = pd.Timedelta(minutes=15)


def local_time(value):
    t = pd.Timestamp(value)
    if t.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    t = t.tz_convert('America/Sao_Paulo')
    if t != t.floor('15min'):
        raise ValueError('Timestamp must align to 15 minutes')
    return t


class ForecastEngine:
    def __init__(self, config):
        from station_forecasts.predict import Forecaster
        self.root = ROOT
        self.config = config
        self.model = Forecaster(config['station_id'], config['model_version'])
        manifest = json.loads((ROOT / config['profile_path']).read_text(encoding='utf-8'))
        if manifest['station_id'] != config['station_id']:
            raise ValueError('Dataset station identity mismatch')
        self.physical = manifest['equipment']
        self.balancer_state = BalancerState()  # Own state, allocator deliberately unavailable.
        self.allocation = {e['id']: None for e in self.physical['evse']}
        self.cache = {}
        self.history = None
        folder = ROOT / 'data/synthetic_profiles' / config['profile']
        for name in ['building.csv', 'ev.csv', 'energy.csv']:
            if digest(folder / name) != manifest['outputs_sha256'][name]:
                raise ValueError('Dataset integrity mismatch: ' + name)
        self.building = pd.read_csv(folder / 'building.csv')
        self.ev = pd.read_csv(folder / 'ev.csv')
        self.energy = pd.read_csv(folder / 'energy.csv')
        self.times = pd.DatetimeIndex(pd.to_datetime(self.building.timestamp))
        self.model_identity = {'station_id': config['station_id'], 'path': config['model_path'],
                               'freeze_sha256': config['model_freeze_sha256'], 'selection': self.model.selection}

    def run_cycle(self, issue_time, current=None, mode='NORMAL'):
        t = local_time(issue_time)
        eligible = self.times < t
        b = self.building.loc[eligible].tail(2689).copy()
        e = self.ev.loc[eligible].tail(2689).copy()
        forecast = self.model.predict(b, e, t)
        # Current fixture is a separate demo measurement, never a future model feature.
        indices = np.flatnonzero(self.times == t)
        if len(indices) != 1:
            raise ValueError('Issue outside available simulation fixture')
        i = int(indices[0]); row = self.ev.iloc[i]; limits = self.physical['evse']
        demands = [{'evse_id': v['id'], 'requested_kw': float(row[f'evse_{j+1:02d}_kw']),
                    'connected': bool(row[f'evse_{j+1:02d}_occupied_fraction'] > 0)} for j, v in enumerate(limits)]
        sample = {'building_kw': float(self.building.iloc[i].consumo_predio_kw),
                  'solar_kw': float(self.energy.iloc[i].pv_generation_ac_kw), 'demands': demands}
        if current is not None:
            sample = copy.deepcopy(current)
        validate_current(sample, limits, self.physical['pv']['dc_kwp'])
        demand = sum(x['requested_kw'] for x in sample['demands'] if x['connected'])
        house = self.config['station_id'] == 'DEMO_CASA_001'
        extension = dict(schema_version='1.0', station_id=self.config['station_id'],
            model_identity=self.model_identity, equipment=self.physical,
            dispatch_available=False, load_balancer_available=False,
            unavailable_reason='Frozen MPC/LB require four 22kW EVSEs and aggregate battery; no compatible dispatch implemented.',
            measured_demand_kw=demand, measurement_origin='SIMULATED',
            ev_prediction_policy='current-demand guard; learned forecast diagnostic only' if house else 'experimental forecast; no dispatch',
            ev_motor2_autonomous_approved=False, residential_ev_recall=0.06778169014084508 if house else None,
            immediate_demand_kw=demand,
            conservative_capacity_envelope_kw=[max(demand, float(v)) for v in forecast.potencia_solicitada_alta_kw] if house else None,
            envelope_is_quantile=False, envelope_is_command=False,
            evses=copy.deepcopy(sample['demands']))
        # Preserve legacy field names. Unknown dispatch stays null, never fictitious zero.
        numeric = {k: None for k in ['battery_soc_pct','battery_charge_kw','battery_discharge_kw',
            'grid_import_kw','grid_export_kw','ev_block_limit_kw','battery_soc_after_pct',
            'energy_balance_error_kw','ev_unserved_kw','ev_served_kw']}
        numeric.update(building_kw=sample['building_kw'], solar_kw=sample['solar_kw'], ev_demand_kw=demand,
            evse_setpoints_kw=[None] * len(limits), evses={x['evse_id']: x for x in sample['demands']})
        visual = dict(valid=False, commands_valid=False, solar_active=sample['solar_kw'] > 0,
            building_active=sample['building_kw'] > 0, grid_importing=None, grid_exporting=None,
            battery_charging=None,battery_discharging=None,battery_flow='unknown',grid_flow='unknown',
            solar='active' if sample['solar_kw'] > 0 else 'inactive',
            evses={x['id']: 'unknown' for x in limits})
        for j in range(1,5):
            visual[f'evse_{j}_active']=None; visual[f'evse_{j}_fault']=None
        message = dict(code='DISPATCH_UNAVAILABLE',severity='warning',text=extension['unavailable_reason'],reason_codes=['PROFILE_INCOMPATIBLE'])
        result = dict(output_version='1.0', timestamp=t.isoformat(), decision_time=t.isoformat(),
            profile=self.config['profile'],mode=mode,status='forecast_only',execution_allowed=False,
            numeric_state=numeric,visual_state=visual,maquette_state=copy.deepcopy(visual),
            forecasts=dict(records=json_safe(forecast.rename(columns={'timestamp_previsto':'timestamp','consumo_previsto_kw':'building_kw'}).assign(solar_previsto_kw=None).to_dict('records')),steps=48,interval_minutes=15,timezone='America/Sao_Paulo',solar_metadata={'available':False},solar_source='unavailable',solar_stale=True),management={'execution_allowed':False},
            load_balancer={'available':False,'setpoints_kw':copy.deepcopy(self.allocation)},
            events=[dict(code='RESIDENTIAL_EV_LOW_RECALL' if house else 'DISPATCH_UNAVAILABLE',origin='SIMULATED')],
            messages=[message],primary_message=message,reason_codes=['PROFILE_INCOMPATIBLE'],
            presentation_metadata={'hardware_commands_sent':False,'setpoints_are_limits':True,'llm_calls':0},
            provenance={'origin':'SIMULATED','input_source':'local synthetic fixture / explicit simulated current',
                        'history_available_through':(t-STEP).isoformat(),'station_id':self.config['station_id']},
            station_extension=extension)
        self.history=(b,e)
        self.cache={'issue_time':t.isoformat(),'forecast_rows':48}
        return result


def validate_current(sample, limits, solar_limit):
    if set(sample) != {'building_kw','solar_kw','demands'}:
        raise ValueError('Current sample fields mismatch')
    for key in ['building_kw','solar_kw']:
        if not np.isfinite(sample[key]) or sample[key] < 0:
            raise ValueError('Invalid current power')
    if sample['solar_kw'] > solar_limit:
        raise ValueError('Solar outside station envelope')
    byid={d['evse_id']:d for d in sample['demands']}
    if len(byid)!=len(sample['demands']) or set(byid)!={x['id'] for x in limits}:
        raise ValueError('Exactly the station EVSEs are required')
    for x in limits:
        d=byid[x['id']];v=d['requested_kw']
        if set(d)!={'evse_id','requested_kw','connected'} or type(d['connected']) is not bool or not np.isfinite(v) or not 0 <= v <= x['max_kw'] or (not d['connected'] and v != 0):
            raise ValueError('EVSE outside station envelope')


class CommercialEngine(GIEEngine):
    def __init__(self):
        from motor_consumo.predict import MotorHibrido
        from motor_carregadores_v2.predict import MotorCarregadores
        self.motor1=MotorHibrido();self.motor2=MotorCarregadores()
        super().__init__(components=Components(self.motor1,self.motor2,None))
        self.building=pd.read_csv(ROOT/'data/consumo_predio_6_meses.csv')
        self.ev=pd.read_csv(ROOT/'data/demanda_carregadores_6_meses.csv')
        self.times=pd.DatetimeIndex(pd.to_datetime(self.building.timestamp)).tz_localize('America/Sao_Paulo')
        self.history=None;self.cache={}
        self.model_identity={'station_id':'Commercial_HighAutonomy_V2','motor1':'motor_consumo frozen hybrid',
                             'motor2':'motor_carregadores_v2 frozen selector','policy':'Commercial_HighAutonomy_V2'}

    def run_cycle(self, issue_time, current=None, mode='NORMAL'):
        t=local_time(issue_time);eligible=self.times<t
        b=self.building.loc[eligible].tail(3000).copy();e=self.ev.loc[eligible].tail(3000).copy()
        # Explicit local-zone conversion required by frozen naive-time predictors.
        for frame in [b,e]:
            frame['timestamp']=pd.to_datetime(frame.timestamp).dt.tz_localize('America/Sao_Paulo').dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None)
        ix=np.flatnonzero(self.times==t)
        if len(ix)!=1:raise ValueError('Issue outside commercial synthetic fixture')
        i=int(ix[0]);demand=float(self.ev.iloc[i].potencia_solicitada_kw)
        n=int(self.ev.iloc[i].carregadores_ocupados)
        demands=[dict(evse_id=f'EVSE{j}',connected=j<=n,requested_kw=min(22.,demand/max(1,n)) if j<=n else 0.) for j in range(1,5)]
        sample=current or dict(building_kw=float(self.building.iloc[i].consumo_predio_kw),solar_kw=0.,demands=demands)
        validate_current(sample,[dict(id=f'EVSE{j}',max_kw=22.) for j in range(1,5)],500.)
        h=History(b,e,{'origin':'SIMULATED','station_id':'Commercial_HighAutonomy_V2','timezone_adapter':'America/Sao_Paulo -> local naive, no shift'})
        devices=[EVSEState(x['evse_id'],x['connected'],max_power_kw=x['requested_kw'],vehicle_max_kw=22.,connected_since=t.isoformat() if x['connected'] else None) for x in sample['demands']]
        now=CurrentState(t,sample['building_kw'],sum(x['requested_kw'] for x in sample['demands']),sample['solar_kw'],50.,devices,provenance={'origin':'SIMULATED','SOC':'explicit independent 50 percent fixture'})
        self.components.solar=LocalSolar(pd.DataFrame({'solar_previsto_kw':[sample['solar_kw']]*48},index=pd.date_range(t,periods=48,freq='15min')))
        result=super().run_cycle(t,h,now,mode)
        result['provenance'].update(origin='SIMULATED',station_id='Commercial_HighAutonomy_V2',solar='constant explicit demo forecast; no network',SOC='independent 50 percent fixture')
        self.history=(b,e);self.cache={'issue_time':t.isoformat()}
        return result


def make_control(config):
    if config['kind']=='commercial':
        engine=CommercialEngine()
    elif config['kind']=='baseline':
        from gie_provisioning.engine import BaselineEngine
        engine=BaselineEngine(config)
    else:
        from gie_energy_v3.engine import EnergyEngine
        engine=EnergyEngine(config)
    return GIEControl(engine=engine)
