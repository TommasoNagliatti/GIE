"""96 real MPC cycles per profile through isolated workers; restart at midday."""
import concurrent.futures as cf,json,tempfile,time,gzip,argparse
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from gie_multistation.manager import Manager
from gie_multistation.registry import ROOT
OUT=ROOT/'reports/energy_v3/v1'

def run_station(manager,sid,start,out):
    initial=manager.start(sid);rows=[];plans=[];started=time.perf_counter();t=pd.Timestamp(start)
    for k in range(96):
        reply=manager.request(sid,'cycle',{'issue_time':(t+pd.Timedelta(minutes=15*k)).isoformat()})
        result=reply['state'];m=result['management']
        if not result['execution_allowed']:raise RuntimeError(sid+' cycle '+str(k)+': '+json.dumps(m))
        first=m['first_decision'];row={'timestamp':result['timestamp'],**{x:first[x] for x in ['building_kw','solar_available_kw','solar_used_kw','solar_curtailed_kw','grid_import_kw','grid_export_kw','ev_requested_kw','ev_served_kw','balance_error_kw']}}
        for bid,b in first['batteries'].items():
            for key,value in b.items():row[bid+'_'+key]=value
        for eid,value in first['evse_setpoints_kw'].items():row[eid+'_authorized_kw']=value
        row.update(max_horizon_balance_error_kw=m['verification']['max_balance_error_kw'],max_horizon_energy_error_kwh=m['verification']['max_energy_error_kwh'],solve_ms=m['elapsed_ms'])
        rows.append(row);plans.append({'timestamp':row['timestamp'],'plan':m['plan'],'stages':m['stages'],'verification':m['verification']})
        if k==47:
            saved=reply['simulation_state'];old=reply['generation'];reply=manager.restart(sid)
            assert reply['simulation_state']==saved and reply['generation']!=old
        if (k+1)%24==0:print(sid,k+1,'cycles verified',flush=True)
    frame=pd.DataFrame(rows);folder=out/sid;folder.mkdir(parents=True,exist_ok=True);frame.to_csv(folder/'cycles_24h.csv',index=False)
    with gzip.open(folder/'plans_24h.json.gz','wt',encoding='utf-8') as f:json.dump(plans,f,allow_nan=False)
    summary=dict(station_id=sid,origin='SIMULATED',cycles=96,start=start,elapsed_seconds=time.perf_counter()-started,steps_verified=96*48,
        initial_state=initial['simulation_state'],final_state=manager.request(sid,'state')['simulation_state'],restart_after_cycle=48,restart_preserved_state=True,
        totals_kwh={key:float(frame[key].sum()*.25) for key in ['building_kw','solar_available_kw','solar_used_kw','solar_curtailed_kw','grid_import_kw','grid_export_kw','ev_requested_kw','ev_served_kw']},
        max_balance_error_kw=float(frame.max_horizon_balance_error_kw.max()),max_energy_error_kwh=float(frame.max_horizon_energy_error_kwh.max()),solve_ms_mean=float(frame.solve_ms.mean()),solve_ms_max=float(frame.solve_ms.max()),physical_dispatch=False,hardware_commands_sent=False)
    (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');plot(frame,sid,folder/'diagnostics_24h.png');manager.stop(sid);return summary

def plot(f,sid,path):
    x=pd.to_datetime(f.timestamp);fig,axes=plt.subplots(4,2,figsize=(16,14),layout='constrained');ax=axes.ravel()
    for k in [k for k in f if k.endswith('_soc_after')]:ax[0].plot(x,100*f[k],label=k.removesuffix('_soc_after'))
    if not ax[0].lines:ax[0].text(.5,.5,'No battery installed',ha='center',transform=ax[0].transAxes)
    ax[0].set(title='Individual simulated SOC',ylabel='%')
    groups=[(['grid_import_kw','grid_export_kw'],'Grid'),(['solar_available_kw','solar_used_kw','solar_curtailed_kw'],'Solar'),(['ev_requested_kw','ev_served_kw'],'EV demand and simulated service'),([k for k in f if k.endswith('_authorized_kw')],'Authorized EVSE limits'),(['building_kw'],'Mandatory building load'),([k for k in f if k.endswith('_charge_kw') or k.endswith('_discharge_kw')],'Individual battery power'),(['balance_error_kw'],'AC balance residual')]
    for a,(keys,title) in zip(ax[1:],groups):
        for key in keys:a.plot(x,f[key],label=key)
        a.set(title=title,ylabel='kW')
    for a in ax:
        if a.lines:a.legend(fontsize=8)
        a.tick_params(axis='x',rotation=25);a.grid(alpha=.2)
    fig.suptitle(sid+' — 24h simulated, Energy V3, no hardware',fontsize=15);fig.savefig(path,dpi=120);plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',default='2025-11-01T00:00:00-03:00');p.add_argument('--output',type=Path,default=OUT);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gie-v3-24h-') as td:
        manager=Manager(td,timeout=120)
        try:
            with cf.ThreadPoolExecutor(2) as pool:result=list(pool.map(lambda sid:run_station(manager,sid,args.start,args.output),['DEMO_POSTO_24H_001','DEMO_CASA_001']))
            (args.output/'simulation_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        finally:manager.close()
if __name__=='__main__':main()
