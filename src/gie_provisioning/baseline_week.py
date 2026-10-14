"""Seven days of explicit current fixtures; no historical CSV or personalized model."""
import json,math,tempfile
from pathlib import Path
import pandas as pd
from gie_multistation.manager import Manager
from gie_multistation.registry import ROOT
from .examples import fixture,sample

def main():
    out=ROOT/'reports/provisioning/v1';rows=[]
    c=fixture('NEW_WEEK');c.update(inverters=[dict(inverter_id='I',ac_kw=12)],solar=[dict(solar_id='PV',inverter_id='I',dc_kwp=10)],
        batteries=[dict(battery_id='B',capacity_kwh=17,soc_initial=.6,soc_min=.2,soc_max=.9,charge_kw=4,discharge_kw=4,eta_charge=.94,eta_discharge=.92,inverter_id='I')])
    t=pd.Timestamp('2026-10-01T00:00:00-04:00')
    with tempfile.TemporaryDirectory(prefix='gie-baseline-week-') as td:
        m=Manager(td)
        try:
            m.provision(c);m.start(c['station_id'])
            for k in range(672):
                now=t+k*pd.Timedelta(minutes=15);hour=now.hour+now.minute/60
                body=sample(c,now.isoformat(),building=2.+(3. if 18<=hour<21 else 0.),solar=8*max(0.,math.sin(math.pi*(hour-6)/12)))
                for j,d in enumerate(body['current']['demands']):
                    d['connected']=18<=hour<21 and j%2==now.day%2;d['requested_kw']=c['chargers'][j]['max_kw'] if d['connected'] else 0.
                if now.day==3:body['current']['battery_available']={'B':False}
                if now.day==5:body['current']['inverter_available']={'I':False}
                reply=m.request(c['station_id'],'cycle',body);r=reply['state'];management=r['management']
                if not r['execution_allowed']:raise RuntimeError(json.dumps(management))
                f=management['first_decision'];rows.append(dict(timestamp=now.isoformat(),building_kw=f['building_kw'],solar_used_kw=f['solar_used_kw'],grid_import_kw=f['grid_import_kw'],grid_export_kw=f['grid_export_kw'],ev_served_kw=f['ev_served_kw'],soc_after=f['batteries']['B']['soc_after'],max_balance_error_kw=management['verification']['max_balance_error_kw'],max_energy_error_kwh=management['verification']['max_energy_error_kwh'],solve_ms=management['elapsed_ms']))
                if k==335:
                    saved=reply['simulation_state'];assert m.restart(c['station_id'])['simulation_state']==saved
                if (k+1)%96==0:print('NEW_WEEK',k+1,'cycles verified',flush=True)
            frame=pd.DataFrame(rows);frame.to_csv(out/'baseline_week.csv',index=False)
            result=dict(cycles=672,verified_steps=672*48,station_id=c['station_id'],origin='SIMULATED',personalized=False,source='deterministic explicit current fixtures, not historical data',restart_verified=True,
                max_balance_error_kw=float(frame.max_balance_error_kw.max()),max_energy_error_kwh=float(frame.max_energy_error_kwh.max()),solve_ms_mean=float(frame.solve_ms.mean()),solve_ms_max=float(frame.solve_ms.max()),final_state=m.request(c['station_id'],'state')['simulation_state'],physical_dispatch=False)
            (out/'baseline_week_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        finally:m.close()
if __name__=='__main__':main()
