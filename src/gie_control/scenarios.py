"""Explicit independent demonstrations, not a new dataset or continuous day."""
from copy import deepcopy
from dataclasses import replace
import pandas as pd
from load_balancer import EVSEState
from load_balancer.state import BalancerState
from integracoes.weather.models import horizon
from integracoes.solar.models import SolarForecast
from .outputs import standardize
from .profile import load_profile

def inputs(hour,building=140,solar=0,ev=44,soc=60,connected=4,fault=None):
    return dict(timestamp=f'2026-07-15 {hour}:00',building_kw=building,solar_kw=solar,
                ev_demand_kw=ev,battery_soc_pct=soc,connected=connected,fault=fault)

SCENES=[
 ('01','Madrugada / baixa atividade',inputs('00:00',70,0,0,60,0),['solar_off','ev_off','discharge']),
 ('02','Rede como backup',inputs('02:00',110,0,0,20,0),['import','battery_idle']),
 ('03','Amanhecer',inputs('06:00',90,30,0,60,0),['solar_on','discharge']),
 ('04','Solar atendendo o prédio',inputs('08:00',120,120,0,60,0),['solar_on','battery_idle','grid_idle']),
 ('05','Chegada de veículos',inputs('08:15',130,100,44,60,4),['all_ev','discharge']),
 ('06','Excedente solar',inputs('09:00',140,260,44,60,4),['charge']),
 ('07','Forte geração solar',inputs('12:00',160,460,66,50,4),['charge','all_ev']),
 ('08','Exportação',inputs('12:15',140,480,44,95,4),['export','battery_idle']),
 ('09','Queda de geração solar',inputs('13:00',150,25,44,60,4),['discharge']),
 ('10','Pico de consumo do prédio',inputs('14:00',420,100,44,60,4),['discharge']),
 ('11','Pico de EVs',inputs('14:15',150,100,88,60,4),['all_ev','discharge']),
 ('12','Pico combinado',inputs('17:00',480,20,88,60,4),['discharge','import']),
 ('13','Falha de EVSE 3',inputs('17:15',140,50,44,60,4,'EVSE3'),['fault3','redistribution']),
 ('14','Recuperação do EVSE',inputs('17:30',140,50,44,60,4),['all_ev','recovered3']),
 ('15','Bateria no mínimo físico',inputs('18:00',180,0,44,20,4),['import','battery_idle']),
 ('16','Final do dia / noite',inputs('21:00',100,0,22,60,2),['solar_off','discharge']),
]

EVENTS={'EV_PEAK':'Pico EV','BUILDING_PEAK':'Pico do prédio','SOLAR_DROP':'Redução solar',
        'SOLAR_STRONG':'Solar forte',**{f'FAULT_EVSE{i}':f'Falha EVSE {i}' for i in range(1,5)},
        'RECOVER_EVSES':'Recuperar EVSEs','SOC_HIGH':'SOC alto demonstrativo','SOC_LOW':'SOC baixo demonstrativo'}

def apply_event(source,code):
    d=deepcopy(source)
    if code not in EVENTS:raise ValueError('Unknown demo event')
    if code=='EV_PEAK':d.update(ev_demand_kw=88,connected=4)
    elif code=='BUILDING_PEAK':d['building_kw']=420
    elif code=='SOLAR_DROP':d['solar_kw']=0
    elif code=='SOLAR_STRONG':d['solar_kw']=480
    elif code.startswith('FAULT_'):
        d['faults']=list(dict.fromkeys(d.get('faults',[])+([d['fault']] if d.get('fault') else [])+[code.removeprefix('FAULT_')]))
        d['fault']=None
    elif code=='RECOVER_EVSES':d.update(fault=None,faults=[],connected=4)
    elif code=='SOC_HIGH':d['battery_soc_pct']=95
    elif code=='SOC_LOW':d['battery_soc_pct']=20
    return d

class FrameForecast:
    def __init__(self,frame):self.frame=frame
    def predict(self,*args):return self.frame.copy(deep=True)

class LocalSolar:
    def __init__(self,frame):self.frame=frame
    def forecast(self,t):return SolarForecast(self.frame.copy(deep=True),'explicit_demo_forecast',False,
               {'demo':True,'network_used':False,'forecast_assumption':'constant solar/EV; building peaks above 200 kW last one interval'})

def execute_demo(source,mode='MANUAL_DEMO',root=None,previous=None):
    """Same frozen V2 MPC/runtime/LB. Forecast fixtures are explicitly labelled."""
    from gie_runtime import Components,History,CurrentState
    from motor_gerenciamento_v2.runtime_adapter import run_cycle
    _,cfg=load_profile(root);s=deepcopy(source);t=pd.Timestamp(s['timestamp']);ix=horizon(t)
    naive=ix.tz_localize(None);ev=float(s['ev_demand_kw'])
    a=pd.DataFrame({'timestamp_previsto':naive,'consumo_previsto_kw':s['building_kw']})
    a.loc[a.index[1:],'consumo_previsto_kw']=min(s['building_kw'],200)
    b=pd.DataFrame({'timestamp_previsto':naive,'potencia_solicitada_prevista_kw':ev,'potencia_solicitada_alta_kw':ev,
          'energia_solicitada_prevista_kwh':ev*.25,'carregadores_ocupados_previstos':float(s['connected']),
          'carros_chegando_previstos':0.,'carros_na_fila_previstos':0.,'probabilidade_fila':0.})
    solar=pd.DataFrame({'solar_previsto_kw':s['solar_kw']},index=ix)
    devices=[EVSEState(f'EVSE{i}',i<=s['connected'],'fault' if s.get('fault')==f'EVSE{i}' or f'EVSE{i}' in s.get('faults',[]) else 'available',
                      22.,22.,(t-pd.Timedelta(minutes=30)).isoformat() if i<=s['connected'] else None) for i in range(1,5)]
    current=CurrentState(t,s['building_kw'],ev,s['solar_kw'],s['battery_soc_pct'],devices)
    # Fixture predictors need no historical data; actual frozen model inference does.
    h=pd.DataFrame({'fixture':[0]},index=[t-pd.Timedelta(minutes=15)])
    history=History(h,h,{'kind':'explicit demonstration forecast, no model inference'})
    raw=run_cycle(t,history,current,Components(FrameForecast(a),FrameForecast(b),LocalSolar(solar)),config=cfg,balancer_state=previous)
    raw['events'].append({'timestamp':str(t),'code':'DEMO_INPUT_APPLIED','severity':'info','component':'demo',
                          'context':{'input':s,'independent_scene':True}})
    result=standardize(raw,mode,{'kind':'independent synthetic scenario','input':s,
         'forecasts':'explicit 48-step inputs; solar/EV constant, building peaks above 200 kW last one interval; not Motor 1/2 predictions','core':'frozen High Autonomy V2',
         'SOC':'scenario measurement, not continuous 24h simulation'})
    if result['execution_allowed'] or mode=='PRESENTATION':validate_physics(result)
    return result

def validate_physics(r):
    if not r['execution_allowed']:raise ValueError('Scene blocked: '+str(r['health']))
    n=r['numeric_state'];c=r['management']['physical_config'];eps=1e-5
    assert n['energy_balance_error_kw']<=eps
    assert c['soc_min_pct']-eps<=n['battery_soc_after_pct']<=c['soc_max_pct']+eps
    assert 0<=n['grid_import_kw']<=c['grid_import_max_kw']+eps
    assert 0<=n['grid_export_kw']<=c['grid_export_max_kw']+eps
    assert 0<=n['battery_charge_kw']<=c['battery_charge_max_kw']+eps
    assert 0<=n['battery_discharge_kw']<=c['battery_discharge_max_kw']+eps
    assert n['battery_charge_kw']<=max(0,n['solar_kw']-n['building_kw']-n['ev_served_kw'])+eps
    assert min(n['battery_charge_kw'],n['battery_discharge_kw'])<=eps
    assert min(n['grid_import_kw'],n['grid_export_kw'])<=eps
    assert all(0<=p<=22+eps for p in n['evse_setpoints_kw'])
    assert sum(n['evse_setpoints_kw'])<=n['ev_block_limit_kw']+eps<=88+2*eps
    assert abs(n['solar_kw']+n['grid_import_kw']+n['battery_discharge_kw']-n['building_kw']-n['ev_served_kw']-n['battery_charge_kw']-n['grid_export_kw'])<=eps
    for i,d in enumerate(n['evses'].values()):
        if d['state'] in ('fault','offline','suspended') or not d['connected']:assert n['evse_setpoints_kw'][i]<=eps
    return True

def validate_behavior(result,behaviors):
    n=result['numeric_state'];v=result['visual_state'];eps=1e-5
    check={'solar_off':not v['solar_active'],'solar_on':v['solar_active'],
      'ev_off':sum(n['evse_setpoints_kw'])<=eps,'all_ev':all(v[f'evse_{i}_active'] for i in range(1,5)),
      'charge':v['battery_charging'],'discharge':v['battery_discharging'],
      'import':v['grid_importing'],'export':v['grid_exporting'],
      'battery_idle':v['battery_flow']=='idle','grid_idle':v['grid_flow']=='idle',
      'fault3':v['evse_3_fault'] and n['evse_setpoints_kw'][2]<=eps,
      'redistribution':all(n['evse_setpoints_kw'][i]>11+eps for i in (0,1,3)),
      'recovered3':not v['evse_3_fault'] and n['evse_setpoints_kw'][2]>eps}
    failed=[b for b in behaviors if not check[b]]
    if failed:raise ValueError('Scene behavior mismatch: '+str(failed))
    return True
