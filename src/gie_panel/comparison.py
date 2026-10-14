"""Offline paired experiment. Uses Energy V3 unchanged; never touches station registry.

Run with the core Python: python -B -m gie_panel.comparison
Every run gets a fresh directory and separate A/B checkpoints. The dashboard reads
only a completely validated result published atomically after both runs finish.
"""
import hashlib,json,os,uuid
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/residential_battery/v1'
DT=.25
# Presentation classification only: lexicographic EV tolerance is 1e-5 kWh
# per objective (=4e-5 kW at 15 min). Do not call that residue an EV cut.
EV_LIMIT_DISPLAY_KW=1e-4

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8');os.replace(temp,path)

def summarize(rows):
    if not rows:raise ValueError('Empty comparison')
    total=lambda k:sum(r[k]*DT for r in rows)
    charge=total('charge_kw');discharge=total('discharge_kw')
    loss=charge*.05+discharge*(1/.95-1)
    delta=rows[-1]['stored_kwh']-rows[0]['initial_kwh']
    ac_error=total('solar_used_kw')+total('grid_import_kw')+discharge-total('building_kw')-total('ev_served_kw')-charge-total('grid_export_kw')
    energy_error=charge-discharge-loss-delta
    if abs(ac_error)>1e-4 or abs(energy_error)>1e-4:raise ValueError('Integrated energy balance failed')
    return dict(import_kwh=total('grid_import_kw'),export_kwh=total('grid_export_kw'),solar_kwh=total('solar_kw'),solar_direct_kwh=total('solar_direct_kw'),solar_to_storage_kwh=charge,curtailed_kwh=total('curtailed_kw'),building_kwh=total('building_kw'),ev_requested_kwh=total('ev_demand_kw'),ev_served_kwh=total('ev_served_kw'),ev_unserved_kwh=total('ev_unserved_kw'),charge_kwh=charge,discharge_kwh=discharge,loss_kwh=loss,initial_kwh=rows[0]['initial_kwh'],final_kwh=rows[-1]['stored_kwh'],delta_stored_kwh=delta,equivalent_cycles=discharge/.95/5.4,peak_grid_kw=max(r['grid_import_kw'] for r in rows),limited_intervals=sum(r['ev_unserved_kw']>EV_LIMIT_DISPLAY_KW for r in rows),max_ev_residual_kw=max(r['ev_unserved_kw'] for r in rows),ev_limit_display_threshold_kw=EV_LIMIT_DISPLAY_KW,ac_balance_error_kwh=ac_error,storage_balance_error_kwh=energy_error,max_step_balance_error_kw=max(abs(r['balance_error_kw']) for r in rows))

def run():
    import pandas as pd
    from copy import deepcopy
    from dataclasses import asdict
    from gie_energy_v3.engine import EnergyEngine
    from gie_energy_v3.config import Battery
    from gie_energy_v3.state import SimulatedState
    from gie_multistation.registry import registry,digest
    cfg=registry()['DEMO_CASA_001']
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
    directory=OUT/'runs'/run_id;directory.mkdir(parents=True)
    def progress(**kw):atomic(OUT/'progress.json',dict(run_id=run_id,**kw))
    progress(status='running',completed=0,total=5760)
    try:
        engines={k:EnergyEngine(deepcopy(cfg),directory/(k+'.json')) for k in ('A','B')}
        b=engines['B'];c=deepcopy(b.energy_config)
        c.batteries=[Battery('BAT_RES_HYP',5.4,.2,.2,.95,2.2,2.2,.95,.95,'INV_01')];c.validate()
        b.energy_config=c;b.simulation=SimulatedState(c,directory/'B.json');b.last_issue=None
        assert not engines['A'].energy_config.batteries
        times=pd.date_range('2025-11-01',periods=30*96,freq='15min',tz='America/Sao_Paulo')
        output={'A':[],'B':[]};completed=0;max_guard_error=0.
        for t in times:
            for variant,e in engines.items():
                initial=sum(e.simulation.energy.values())
                r=e.run_cycle(t)
                if not r['execution_allowed']:raise RuntimeError(f'{variant} {t}: {r["management"]}')
                f=r['management']['first_decision'];n=r['numeric_state'];battery=f['batteries']
                charge=sum(v['charge_kw'] for v in battery.values());discharge=sum(v['discharge_kw'] for v in battery.values())
                stored=sum(v['energy_after_kwh'] for v in battery.values())
                # This policy forbids grid charging. Reject ambiguous provenance,
                # rather than silently claiming that imported energy was solar.
                if charge>1e-5 and n['grid_import_kw']>1e-5:raise ValueError('Solar-only provenance violated')
                # Solar first serves AC loads; battery covers the residual.
                # Export is assigned to PV (battery export forbidden by policy).
                direct=f['solar_used_kw']-n['grid_export_kw']-charge
                if direct < -1e-5:raise ValueError('Negative solar allocation')
                row=dict(timestamp=t.isoformat(),building_kw=n['building_kw'],solar_kw=n['solar_kw'],solar_used_kw=f['solar_used_kw'],curtailed_kw=f['solar_curtailed_kw'],ev_demand_kw=n['ev_demand_kw'],ev_served_kw=n['ev_served_kw'],ev_unserved_kw=n['ev_unserved_kw'],grid_import_kw=n['grid_import_kw'],grid_export_kw=n['grid_export_kw'],charge_kw=charge,discharge_kw=discharge,initial_kwh=initial,stored_kwh=stored,soc_pct=stored/5.4*100 if variant=='B' else None,solar_direct_kw=direct,balance_error_kw=f['balance_error_kw'])
                output[variant].append(row);completed+=1
                max_guard_error=max(max_guard_error,abs(r['management']['verification']['max_balance_error_kw']))
            for k in ('building_kw','solar_kw','ev_demand_kw'):
                if output['A'][-1][k]!=output['B'][-1][k]:raise ValueError('Paired inputs differ: '+k)
            if completed%96==0:progress(status='running',completed=completed,total=5760)
        days={}
        for row in output['A']:days[row['timestamp'][:10]]=days.get(row['timestamp'][:10],0)+row['ev_demand_kw']*DT
        with_ev=next(d for d,v in days.items() if v>1e-5);without_ev=next(d for d,v in days.items() if v<=1e-5)
        windows={'Dia com EV':(with_ev,with_ev),'Dia sem EV':(without_ev,without_ev),'Uma semana':('2025-11-01','2025-11-07'),'Novembro · 30 dias':('2025-11-01','2025-11-30')}
        periods={}
        for name,(start,end) in windows.items():
            cases={v:[r for r in rows if start<=r['timestamp'][:10]<=end] for v,rows in output.items()}
            periods[name]=dict(start=start,end=end,rows=cases,summary={v:summarize(rows) for v,rows in cases.items()})
        manifest=ROOT/cfg['profile_path']
        inputs={str(p.relative_to(ROOT)):digest(p) for p in sorted(manifest.parent.glob('*.csv'))}
        inputs[str(manifest.relative_to(ROOT))]=digest(manifest)
        for p in sorted((ROOT/cfg['model_path']).rglob('*')):
            if p.is_file():inputs[str(p.relative_to(ROOT))]=digest(p)
        result=dict(version=1,run_id=run_id,origin='SIMULATED',engine='Energy V3 unchanged; 48-step rolling MPC',periods=periods,configurations={v:asdict(e.energy_config) for v,e in engines.items()},inputs_sha256=inputs,max_guard_balance_error_kw=max_guard_error,cycles_per_case=len(times),checkpoint_paths={v:str((directory/(v+'.json')).relative_to(ROOT)) for v in engines},notes=['Novembro de 2025: mês completo de avaliação, não estimativa anual.', 'Dias e semana são recortes da mesma trajetória mensal; SOC inicial/final é mostrado em cada recorte.', 'B inicia em SOC mínimo (20%); nenhuma energia inicial utilizável gratuita.', 'Eficiência 95% por sentido é hipótese AC conservadora; não garantia de catálogo.', 'Sem tarifa configurada: não há estimativa financeira ou de retorno.'])
        for v,rows in output.items():pd.DataFrame(rows).to_csv(directory/(v+'.csv'),index=False)
        atomic(directory/'result.json',result);atomic(OUT/'result.json',result)
        progress(status='complete',completed=completed,total=5760)
    except Exception as exc:
        progress(status='failed',error=str(exc),completed=locals().get('completed',0),total=5760);raise

if __name__=='__main__':run()
