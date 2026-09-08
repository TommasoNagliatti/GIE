"""One real-components cycle with explicitly labelled replay/telemetry fixtures."""
import sys,os,json,io,unittest,hashlib,math
from pathlib import Path
from time import perf_counter
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from gie_runtime import Components,History,CurrentState,run_gie_cycle
from load_balancer import EVSEState

def main():
    out=ROOT/'outputs/gie_runtime/v1'
    reports=[];test_results={}
    for name in ('gie_runtime','motor_gerenciamento','load_balancer','integracoes'):
        suite=unittest.TestLoader().discover(str(ROOT/'tests'/name))
        stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        reports.append(name+'\n'+stream.getvalue());test_results[name]=dict(tests=result.testsRun,passed=result.wasSuccessful())
        if not result.wasSuccessful():raise RuntimeError(name+' tests failed; real cycle aborted.')
    (out/'test_results.txt').write_text('\n'.join(reports),encoding='utf-8')
    # Dataset ends in June. Preserve source values/order and weekday, replay
    # timestamps in memory only. This is not live telemetry or a new ML test.
    t=pd.Timestamp.now(tz='America/Sao_Paulo').ceil('15min').tz_localize(None)
    source_time=pd.Timestamp('2026-06-15')+pd.Timedelta(days=t.dayofweek,hours=t.hour,minutes=t.minute)
    delta=t-source_time
    assert delta.total_seconds()%(7*86400)==0
    raw_b=pd.read_csv(ROOT/'data/consumo_predio_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
    raw_e=pd.read_csv(ROOT/'data/demanda_carregadores_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
    def replay(raw):
        data=raw.loc[:source_time-pd.Timedelta(minutes=15)].tail(3000).copy();data.index=data.index+delta
        for key,value in dict(hora=data.index.hour,dia_semana=data.index.dayofweek,fim_de_semana=(data.index.dayofweek>=5).astype(int),mes=data.index.month).items():
            if key in data:data[key]=value
        return data
    history=History(replay(raw_b),replay(raw_e),dict(kind='synthetic historical replay, timestamps shifted in memory',
        source_current_timestamp=str(source_time),shift_days=delta.days,weekdays_preserved=True,
        independent_forecast_evaluation=False,training_data_modified=False))
    current=CurrentState(t,float(raw_b.loc[source_time,'consumo_predio_kw']),float(raw_e.loc[source_time,'potencia_solicitada_kw']),25.,50.,
        [EVSEState(f'EVSE{i}',True,connected_since=t-pd.Timedelta(hours=1)) for i in range(1,5)],
        provenance=dict(kind='demonstration telemetry fixture; no physical inverter/EVSE connection',
            building_and_ev='synthetic official dataset at source_current_timestamp',solar_kw='explicit 25 kW fixture',
            battery_soc='explicit 50% fixture',evses='four connected 22 kW fixture'))
    begin=perf_counter();components=Components.real(ROOT);load_ms=(perf_counter()-begin)*1000
    result=run_gie_cycle(t,history,current,components)
    (out/'cycle.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    if result['status']=='blocked':raise RuntimeError('Cycle blocked: '+str(result['events']))
    if result['health']['solar']['source'] not in ('open_meteo','cache'):raise RuntimeError('No real weather/cache available; real-components acceptance pending.')
    history.building.to_csv(out/'demo_history_building.csv');history.ev.to_csv(out/'demo_history_ev.csv')
    pd.DataFrame(result['forecasts']['records']).to_csv(out/'forecasts_48.csv',index=False)
    pd.DataFrame([{k:v for k,v in p.items() if k!='flows'} for p in result['management']['plan']]).to_csv(out/'mpc_plan_48.csv',index=False)
    provider=components.solar.provider
    (out/'weather_request.json').write_text(json.dumps({'url':provider.last_url,'source':result['health']['solar']['source']},indent=2))
    if provider.last_response is not None:(out/'weather_raw.json').write_text(json.dumps(provider.last_response,ensure_ascii=False,indent=2),encoding='utf-8')
    before=json.loads((out/'preservation_before.json').read_text())
    policy=json.loads((out/'motor3_policy_revision.json').read_text())
    allowed={'src/motor_gerenciamento/'+n for n in policy['changed_files']}
    changed=[p for p,h in before.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert set(changed)<=allowed,changed
    for p in allowed:
        assert hashlib.sha256((out/'motor3_before/src'/Path(p).name).read_bytes()).hexdigest()==before[p]
    preservation=dict(files_checked=len(before),authorized_changes=sorted(changed),unauthorized_changes=[],motor3_previous_sources_verified=True)
    (out/'preservation_validation.json').write_text(json.dumps(preservation,indent=2))
    summary=dict(status=result['status'],decision_time=result['decision_time'],tests=test_results,
        tests_total=sum(v['tests'] for v in test_results.values()),health=result['health'],model_loading_ms=load_ms,
        block_kw=result['management']['ev_block_limit_kw'],setpoints_kw=[result['load_balancer'][f'evse_{i}_kw'] for i in range(1,5)],
        flows=result['flows'],battery_charge_kw=result['management']['battery_charge_kw'],battery_discharge_kw=result['management']['battery_discharge_kw'],
        power_balance_error_kw=result['management']['power_balance_error_kw'],
        history_provenance=history.provenance,current_state_provenance=current.provenance,preservation=preservation)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    diagram(out,result)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

def diagram(out,r):
    os.environ['MPLCONFIGDIR']=str(out/'.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    fig,ax=plt.subplots(figsize=(13,7));ax.set_xlim(0,13);ax.set_ylim(0,7);ax.axis('off')
    def box(x,y,w,h,text,color='#e8f0fa'):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.12',fc=color,ec='#426080'))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=10)
    def arrow(a,b):ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='->',color='#426080',lw=1.5))
    box(.2,4.8,2.5,1,'Motor 1 real\n48 previsões do prédio')
    box(.2,3.1,2.5,1,'Motor 2 real\n48 previsões EV + Q90')
    box(.2,1.4,2.5,1,'Solar: '+r['health']['solar']['source']+'\n48 previsões alinhadas')
    box(4.1,3,3.1,1.9,'Motor 3 V1.1\nMPC: 48 passos\nExecuta somente passo 0\nBateria: somente carga solar')
    for y in (5.3,3.6,1.9):arrow((2.9,y),(4,3.9))
    mg=r['management'];lb=r['load_balancer']
    box(8.4,3.3,4,1.3,f"Load Balancer real\nBloco recebido: {mg['ev_block_limit_kw']:.3f} kW\n"+' / '.join(f"{lb[f'evse_{i}_kw']:.3f}" for i in range(1,5))+' kW')
    arrow((7.35,3.9),(8.2,3.9))
    box(4.1,.4,8.3,1.65,f"Fluxos do passo atual (kW)\nSolar → prédio: {r['flows']['solar_to_building_kw']:.3f}; solar → bateria: {r['flows']['solar_to_battery_kw']:.3f}\nRede → prédio: {r['flows']['grid_to_building_kw']:.3f}; rede → EV: {r['flows']['grid_to_ev_kw']:.3f}\nBateria → prédio: {r['flows']['battery_to_building_kw']:.3f}; bateria → EV: {r['flows']['battery_to_ev_kw']:.3f}",'#eaf5eb')
    arrow((5.65,2.8),(5.65,2.2))
    ax.text(6.5,6.5,'GIE End-to-End V1 — '+r['decision_time'],ha='center',fontsize=15,weight='bold')
    ax.text(6.5,6,'Modelos treinados reais + meteorologia real/cache; histórico e telemetria de demonstração',ha='center',fontsize=10)
    ax.text(6.5,0,'Setpoints EV são limites; os fluxos usam a demanda atual do demonstrador.',ha='center',fontsize=9)
    fig.tight_layout();fig.savefig(out/'cycle_flow.png',dpi=150);plt.close(fig)

if __name__=='__main__':main()
