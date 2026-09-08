"""Prerecorded scenarios; first action only, fresh forecasts and measured SOC each cycle."""
import sys,os,json,hashlib,time,io,unittest
sys.dont_write_bytecode=True
from pathlib import Path
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from motor_gerenciamento.config import Config
from motor_gerenciamento.state import State,Measurements,ForecastInputs
from motor_gerenciamento.optimizer import optimize
from motor_gerenciamento.adapters import FrozenForecastAdapters,aligned_inputs
from motor_gerenciamento.dispatch import apply_first
from motor_gerenciamento.events import from_decision,make_event
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/motor_gerenciamento/v1';C=Config()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def solar_mock(ix):
    h=ix.hour+ix.minute/60
    return np.minimum(C.pv_ac_max_kw,C.pv_installed_kwp*np.maximum(0,np.sin(np.pi*(h-6)/12)))
def tariff_mock(ix):return np.where((ix.hour>=17)&(ix.hour<21),1.2,.35)
def mock_profiles(ix):
    peak=(ix.hour>=17)&(ix.hour<21);day=(ix.hour>=7)&(ix.hour<17)
    return np.where(peak,330.,np.where(day,30.,60.)),np.where(peak,60.,np.where(day,8.,5.)),np.where(peak,88.,np.where(day,20.,12.)),np.where(peak,.8,np.where(day,.2,.05))
def run_loop(mode):
    if mode=='integrated':
        times=pd.date_range('2026-06-15',periods=192,freq='15min')
        building=pd.read_csv(ROOT/'data/consumo_predio_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
        ev=pd.read_csv(ROOT/'data/demanda_carregadores_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
        engines=FrozenForecastAdapters()
    else:times=pd.date_range('2026-07-01',periods=288,freq='15min')
    state=State(50);records=[];plans=[];events=[];initial_energy=100.;fallbacks=[]
    for k,t in enumerate(times):
        origin=t-pd.Timedelta(minutes=15);ix=pd.date_range(t,periods=48,freq='15min');started=time.perf_counter()
        solar=pd.Series(solar_mock(ix),index=ix);tariff=pd.Series(tariff_mock(ix),index=ix);credit=pd.Series(.08,index=ix)
        if mode=='integrated':
            # Only past is supplied. Future actual values below are used after optimization.
            a,b=engines.predict(building.loc[:origin].copy(),ev.loc[:origin].copy(),origin)
            m=Measurements(origin,float(building.loc[origin,'consumo_predio_kw']),float(ev.loc[origin,'potencia_entregue_kw']),float(solar_mock(pd.DatetimeIndex([origin]))[0]))
            inp=aligned_inputs(a,b,solar,tariff,credit,m,{'mode':'integrated','solar_and_tariff':'fictitious deterministic mock','engines':'frozen Motor1 V2 / Motor2 V2'})
        else:
            b,e,q,r=mock_profiles(ix);last=mock_profiles(pd.DatetimeIndex([origin]))
            inp=ForecastInputs(ix,b,e,q,r,solar,tariff,credit,Measurements(origin,float(last[0][0]),float(last[1][0]),float(solar_mock(pd.DatetimeIndex([origin]))[0])),{'mode':'mock_stress','all_loads_solar_tariffs':'fictitious perfect forecasts'})
        forecast_ms=(time.perf_counter()-started)*1000
        result=optimize(inp,state,C)
        if not result['execution_allowed']:raise RuntimeError('No safe schedule: '+str(result))
        # The plant reveals this interval only after scheduling. No true future in MPC.
        if mode=='integrated':actual_b=float(building.loc[t,'consumo_predio_kw']);actual_ev=float(ev.loc[t,'potencia_solicitada_kw'])
        else:actual_b=float(inp.building_kw[0]);actual_ev=float(inp.ev_expected_kw[0])
        actual_pv=float(solar_mock(pd.DatetimeIndex([t]))[0])
        applied=apply_first(result['first_decision'],state,actual_b,actual_ev,actual_pv,C)
        for j,plan in enumerate(result['plan']):
            plans.append({'decision_time':str(t),'step':j,'applied':j==0,**{key:value for key,value in plan.items() if key!='flows'}})
        row={key:value for key,value in applied.items() if key!='flows'}
        row.update(applied['flows']);row.update(solver_runtime_ms=result['solver_runtime_ms'],controller_runtime_ms=result['controller_runtime_ms'],
            forecast_runtime_ms=forecast_ms,fallback_used=result['fallback_used'],applied_plan_step=0,horizon_steps=48,
            forecast_building_kw=float(inp.building_kw[0]),forecast_ev_kw=float(inp.ev_expected_kw[0]),
            energy_cost=tariff.iloc[0]*applied['grid_import_plan_kw']*.25-credit.iloc[0]*applied['grid_export_plan_kw']*.25)
        records.append(row)
        events.extend(from_decision(applied,state,C,result['fallback_used']))
        if applied['safety_override']:events.append(make_event('SAFETY_OVERRIDE','warning','Comando ajustado à medição realizada para manter limites e evitar descarga para exportação.',t,
            {'planned_charge_kw':result['battery_charge_kw'],'executed_charge_kw':applied['battery_charge_kw'],
             'planned_discharge_kw':result['battery_discharge_kw'],'executed_discharge_kw':applied['battery_discharge_kw']}))
        if result['fallback_used']:fallbacks.append({'timestamp':str(t),'reason':result['fallback_reason']})
        state=State(applied['battery_soc_after_pct'],applied['battery_charge_kw'],applied['battery_discharge_kw'])
        if mode=='integrated':
            # Only in-memory observed delivery changes. Sessions/queue remain exogenous.
            ev.loc[t,'potencia_entregue_kw']=applied['ev_served_kw'];ev.loc[t,'energia_entregue_kwh']=applied['ev_served_kw']*.25
        if k==32:write('example_output_'+mode+'.json',result)
        if k%24==0:print(f'{mode}: {k+1}/{len(times)} ciclos; SOC {state.battery_soc_pct:.1f}%; solver {result["solver_runtime_ms"]:.1f} ms',flush=True)
    df=pd.DataFrame(records);df.to_csv(OUT/(mode+'_closed_loop.csv'),index=False,float_format='%.8f')
    pd.DataFrame(plans).to_csv(OUT/(mode+'_plans_48.csv'),index=False,float_format='%.8f')
    write(mode+'_events.json',events)
    balance=df.solar_utilizado_kw+df.grid_import_plan_kw+df.battery_discharge_kw-df.building_kw-df.ev_served_kw-df.battery_charge_kw-df.grid_export_plan_kw
    increments=df.battery_energy_kwh.to_numpy()-np.r_[initial_energy,df.battery_energy_kwh.to_numpy()[:-1]]
    dynamics=increments-.25*(df.battery_charge_kw.to_numpy()*.95-df.battery_discharge_kw.to_numpy()/.95)
    assert np.abs(balance).max()<C.tolerance and np.abs(dynamics).max()<C.tolerance
    assert df.battery_soc_after_pct.between(20-1e-6,95+1e-6).all()
    for col,cap in [('grid_import_plan_kw',350),('grid_export_plan_kw',150),('ev_block_limit_kw',88),('battery_charge_kw',100),('battery_discharge_kw',100)]:assert df[col].between(-1e-6,cap+1e-6).all()
    assert (np.minimum(df.battery_charge_kw,df.battery_discharge_kw)<C.simultaneity_kw).all()
    assert (np.minimum(df.grid_import_plan_kw,df.grid_export_plan_kw)<C.simultaneity_kw).all()
    assert np.array_equal(df.solar_utilizado_kw,df.solar_disponivel_kw)
    summary={'mode':mode,'cycles':len(df),'hours':len(df)*.25,'plans_48_recomputed':len(df),'only_step_zero_applied':True,
        'solver_mean_ms':float(df.solver_runtime_ms.mean()),'solver_p95_ms':float(df.solver_runtime_ms.quantile(.95)),
        'solver_max_ms':float(df.solver_runtime_ms.max()),'controller_mean_ms':float(df.controller_runtime_ms.mean()),
        'forecast_mean_ms':float(df.forecast_runtime_ms.mean()),'soc_min_pct':float(df.battery_soc_after_pct.min()),'soc_max_pct':float(df.battery_soc_after_pct.max()),
        'grid_import_max_kw':float(df.grid_import_plan_kw.max()),'grid_export_max_kw':float(df.grid_export_plan_kw.max()),
        'battery_charge_max_kw':float(df.battery_charge_kw.max()),'battery_discharge_max_kw':float(df.battery_discharge_kw.max()),
        'export_total_kwh':float(df.grid_export_plan_kw.sum()*.25),'ev_unserved_kwh':float(df.ev_unserved_kw.sum()*.25),
        'grid_over_target_kwh':float(df.grid_over_target_kw.sum()*.25),'safety_overrides':int(df.safety_override.sum()),
        'fallbacks':fallbacks,'balance_error_max_kw':float(np.abs(balance).max()),'soc_dynamics_error_max_kwh':float(np.abs(dynamics).max()),
        'solar_fully_used':True,'events':pd.Series([e['code'] for e in events]).value_counts().to_dict()}
    write(mode+'_summary.json',summary);plot(df,mode);return summary
def plot(df,mode):
    os.environ['MPLCONFIGDIR']=str(OUT/'.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    t=pd.to_datetime(df.timestamp);fig,axes=plt.subplots(5,1,figsize=(14,13),sharex=True)
    for col,label in [('building_kw','Prédio'),('ev_served_kw','EV atendido'),('solar_utilizado_kw','Solar (mock)')]:axes[0].plot(t,df[col],label=label)
    axes[1].fill_between(t,0,df.battery_charge_kw,label='Carga',alpha=.7);axes[1].fill_between(t,0,-df.battery_discharge_kw,label='Descarga',alpha=.7)
    axes[2].plot(t,df.grid_import_plan_kw,label='Importação');axes[2].plot(t,-df.grid_export_plan_kw,label='Exportação (-)')
    axes[2].axhline(300,color='orange',ls='--',label='Alvo 300');axes[2].axhline(350,color='red',ls=':',label='Físico 350')
    axes[3].plot(t,df.battery_soc_after_pct,label='SOC');axes[3].axhline(20,color='red',ls=':');axes[3].axhline(95,color='red',ls=':');axes[3].axhline(30,color='orange',ls='--',label='Reserva 30%');axes[3].set_ylim(15,100)
    for col,label in [('ev_expected_kw','Demanda realizada'),('ev_served_kw','EV atendido'),('ev_block_limit_kw','Limite bloco')]:axes[4].plot(t,df[col],label=label)
    for i,ax in enumerate(axes):ax.set_ylabel('SOC (%)' if i==3 else 'kW');ax.legend(loc='upper right',fontsize=8,ncol=3);ax.grid(alpha=.2)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %Hh'))
    title='48h com Motores 1/2 congelados' if mode=='integrated' else '72h de estresse totalmente fictício'
    fig.suptitle('Motor 3 V1 | '+title+' | solar e tarifas mock');fig.tight_layout();fig.savefig(OUT/(mode+'_closed_loop.png'),dpi=140);plt.close(fig)
def main():
    prereg=json.loads((OUT/'preregistration.json').read_text())
    assert sha(ROOT/'src/motor_gerenciamento/config.py')==prereg['config_sha256'],'Weights/config altered after preregistration.'
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests/motor_gerenciamento'),pattern='test_*.py')
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/'test_results.txt').write_text(stream.getvalue(),encoding='utf-8')
    write('test_results.json',{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful()})
    if not result.wasSuccessful():raise RuntimeError('Unit tests failed; closed loop aborted.')
    a=run_loop('integrated');b=run_loop('mock_stress')
    ix=pd.date_range('2026-08-01',periods=48,freq='15min')
    fixture=ForecastInputs(ix,np.full(48,100.),np.full(48,20.),np.full(48,40.),np.full(48,.4),np.zeros(48),np.full(48,.5),np.full(48,.08))
    def unavailable(*args,**kwargs):raise RuntimeError('deliberate failure for fallback demonstration')
    write('fallback_example.json',optimize(fixture,State(50),solver=unavailable))
    manifest=json.loads((OUT/'preservation_before.json').read_text());changed=[p for p,h in manifest.items() if sha(ROOT/p)!=h]
    assert not changed,changed
    write('preservation_validation.json',{'files_checked':len(manifest),'changed':changed,'unchanged':True,'config_unchanged':sha(ROOT/'src/motor_gerenciamento/config.py')==prereg['config_sha256']})
    write('summary.json',{'integrated':a,'mock_stress':b,'tests_passed':result.testsRun,'protected_files':len(manifest)})
    print(json.dumps({'integrated':a,'mock_stress':b},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
