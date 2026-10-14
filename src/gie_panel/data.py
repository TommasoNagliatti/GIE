"""Server-owned read-only catalogs and display adapters. No path input from clients."""
import copy,gzip,json
from functools import lru_cache
import pandas as pd
from gie_multistation.registry import ROOT
from gie_energy_v3.config import from_manifest
from dataclasses import asdict

COMM='Commercial_HighAutonomy_V2';POST='DEMO_POSTO_24H_001';HOUSE='DEMO_CASA_001';NEW='NEW_NO_HISTORY'
NAMES={COMM:'Prédio comercial',POST:'Posto 24 horas',HOUSE:'Residência',NEW:'Estação BASELINE'}
DATES={'spring':'2025-11-01T00:00:00-03:00','summer':'2025-02-10T00:00:00-03:00','autumn':'2025-05-10T00:00:00-03:00','winter':'2025-08-10T00:00:00-03:00'}

def equipment(config):
    if config['kind']=='baseline':
        from gie_provisioning.contracts import Provision
        return asdict(Provision.model_validate(config['technical']).energy_config())
    if config['kind']=='commercial':
        p=json.loads((ROOT/config['profile_path']).read_text())
        return dict(import_kw=p['grid_import_max_kw'],batteries=[dict(battery_id='LEGACY_BANK',aggregate=True,capacity_kwh=p['battery_capacity_kwh'],soc_min=p['soc_min_pct']/100,soc_max=p['soc_max_pct']/100,charge_kw=p['battery_charge_max_kw'],discharge_kw=p['battery_discharge_max_kw'],available=True)],evses=[dict(evse_id='EVSE'+str(j),max_kw=22,available=True) for j in range(1,5)],inverters=[])
    return asdict(from_manifest(json.loads((ROOT/config['profile_path']).read_text())))

def row_result(row,eq):
    def battery_power(suffix):
        names=[b['battery_id']+'_'+suffix for b in eq['batteries']]
        return sum(row[k] for k in names) if all(k in row and pd.notna(row[k]) for k in names) else None
    n={k:row.get(k) for k in ['building_kw','grid_import_kw','grid_export_kw','ev_served_kw']}
    n.update(solar_kw=row.get('solar_available_kw',row.get('solar_used_kw')),ev_demand_kw=row.get('ev_requested_kw'),ev_unserved_kw=(max(0,row['ev_requested_kw']-row['ev_served_kw']) if 'ev_requested_kw' in row else None),battery_charge_kw=battery_power('charge_kw'),battery_discharge_kw=battery_power('discharge_kw'))
    batteries={b['battery_id']:{k:row.get(b['battery_id']+'_'+k) for k in ['soc_after','energy_after_kwh','charge_kw','discharge_kw']} for b in eq['batteries']}
    powers={e['evse_id']:row.get(e['evse_id']+'_authorized_kw') for e in eq['evses']}
    n['evse_setpoints_kw']=list(powers.values());n['evses']={}
    return dict(timestamp=row['timestamp'],numeric_state=n,management={'first_decision':{'batteries':batteries,'evse_setpoints_kw':powers}},forecasts={'records':[]},visual_state={'commands_valid':False,'valid':True},messages=[],status='saved_simulation',execution_allowed=True,provenance={'origin':'SIMULATED','source':'saved CSV first decisions'})

def catalog(sid):
    if sid==COMM:return [{'id':'commercial','name':'Comparação original V2 · 24h','cycles':96}]
    if sid==NEW:return [{'id':'baseline','name':'BASELINE · ciclo validado sem histórico','cycles':1}]
    return [{'id':s,'name':n,'cycles':96} for s,n in [('spring','Primavera · 24h'),('summer','Verão · 24h'),('autumn','Outono · 24h'),('winter','Inverno · 24h')]]

@lru_cache(maxsize=10)
def replay(sid,scenario,config_json):
    config=json.loads(config_json);eq=equipment(config)
    if scenario not in {c['id'] for c in catalog(sid)}:raise ValueError('Unknown saved scenario')
    if sid==COMM:
        from gie_control.outputs import standardize
        cycles=json.loads((ROOT/'outputs/high_autonomy_v2/comparison/v2_cycles.json').read_text())
        return [standardize(x['cycle'],'SIMULATION',{'origin':'SIMULATED','source':'saved original comparison'}) for x in cycles]
    if sid==NEW:
        return [json.loads((ROOT/'reports/provisioning/v1/four_stations.json').read_text())['new_station_result']]
    if scenario=='spring':
        base=ROOT/'reports/energy_v3/v1'/sid
        rows=pd.read_csv(base/'cycles_24h.csv').to_dict('records')
        with gzip.open(base/'plans_24h.json.gz','rt',encoding='utf-8') as f:plans=json.load(f)
    else:
        rows=pd.read_csv(ROOT/'reports/provisioning/v1/seasonal'/sid/(scenario+'.csv')).to_dict('records');plans=None
    results=[]
    for i,row in enumerate(rows):
        r=row_result(row,eq)
        if plans:
            r['management']['plan']=plans[i]['plan']
            r['forecasts']['records']=[dict(timestamp=(pd.Timestamp(row['timestamp'])+pd.Timedelta(minutes=15*j)).isoformat(),building_kw=p['building_kw'],potencia_solicitada_prevista_kw=p['ev_requested_kw'],solar_previsto_kw=p['solar_available_kw'],origin='SAVED_PLAN_INPUT') for j,p in enumerate(plans[i]['plan'])]
        results.append(r)
    return results

def history_row(r):
    n=r.get('numeric_state') or {};row=dict(timestamp=r.get('timestamp'),**{k:n.get(k) for k in ['building_kw','solar_kw','grid_import_kw','grid_export_kw','ev_demand_kw','ev_served_kw']})
    for bid,b in ((r.get('management') or {}).get('first_decision') or {}).get('batteries',{}).items():row[bid+'_soc_pct']=100*b['soc_after'] if b.get('soc_after') is not None else None
    return row

def display(r,config,source,history=()):
    result=copy.deepcopy(r);result.setdefault('visual_state',{})['commands_valid']=False
    result.update(physical_dispatch=False,hardware_commands_sent=False)
    return dict(station_id=config['station_id'],name=NAMES.get(config['station_id'],config['station_id']),equipment=equipment(config),source=source,result=result,history=list(history))
