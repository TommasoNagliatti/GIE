"""Seasonal days plus seven contiguous days using unchanged Energy V3 workers."""
import concurrent.futures as cf
import json,tempfile,time
from pathlib import Path
import pandas as pd
from gie_multistation.manager import Manager
from gie_multistation.registry import ROOT

OUT=ROOT/'reports/provisioning/v1'
SCENARIOS=[('summer','2025-02-10T00:00:00-03:00',96),('autumn','2025-05-10T00:00:00-03:00',96),('winter','2025-08-10T00:00:00-03:00',96),('spring_week','2025-11-01T00:00:00-03:00',672)]

def run(sid):
    summaries=[]
    for season,start,count in SCENARIOS:
        rows=[];folder=OUT/'seasonal'/sid;folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='gie-seasonal-') as td:
            m=Manager(td,timeout=120)
            try:
                initial=m.start(sid)['simulation_state'];t=pd.Timestamp(start);restart_verified=False
                for k in range(count):
                    reply=m.request(sid,'cycle',dict(issue_time=(t+k*pd.Timedelta(minutes=15)).isoformat()))
                    r=reply['state'];management=r['management']
                    if not r['execution_allowed']:
                        (folder/(season+'_failure.json')).write_text(json.dumps(dict(cycle=k,result=r),indent=2),encoding='utf-8')
                        raise RuntimeError(sid+' '+season+' blocked at '+str(k))
                    first=management['first_decision']
                    row={'timestamp':r['timestamp'],**{key:first[key] for key in ['building_kw','solar_available_kw','solar_used_kw','solar_curtailed_kw','grid_import_kw','grid_export_kw','ev_requested_kw','ev_served_kw','balance_error_kw']}}
                    for bid,b in first['batteries'].items():
                        for key,value in b.items():row[bid+'_'+key]=value
                    for eid,value in first['evse_setpoints_kw'].items():row[eid+'_authorized_kw']=value
                    row.update(solve_ms=management['elapsed_ms'],max_balance_error_kw=management['verification']['max_balance_error_kw'],max_energy_error_kwh=management['verification']['max_energy_error_kwh'])
                    rows.append(row)
                    if k==count//2-1:
                        saved=reply['simulation_state'];generation=reply['generation'];restored=m.restart(sid)
                        assert restored['simulation_state']==saved and restored['generation']!=generation
                        restart_verified=True
                    if (k+1)%96==0:print(sid,season,k+1,'verified cycles',flush=True)
                frame=pd.DataFrame(rows);frame.to_csv(folder/(season+'.csv'),index=False)
                summary=dict(station_id=sid,season=season,start=start,cycles=count,verified_steps=count*48,restart_verified=restart_verified,
                    initial_state=initial,final_state=m.request(sid,'state')['simulation_state'],max_balance_error_kw=float(frame.max_balance_error_kw.max()),max_energy_error_kwh=float(frame.max_energy_error_kwh.max()),
                    solve_ms_mean=float(frame.solve_ms.mean()),solve_ms_max=float(frame.solve_ms.max()),totals_kwh={k:float(frame[k].sum()*.25) for k in ['building_kw','ev_requested_kw','ev_served_kw','solar_used_kw','grid_import_kw','grid_export_kw']},physical_dispatch=False)
                summaries.append(summary)
                (folder/(season+'_summary.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
            finally:m.close()
    return summaries

def main():
    with cf.ThreadPoolExecutor(2) as pool:results=list(pool.map(run,['DEMO_POSTO_24H_001','DEMO_CASA_001']))
    (OUT/'seasonal_summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if __name__=='__main__':main()
