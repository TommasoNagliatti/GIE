"""Runs frozen core in a separate interpreter; only demo outputs are written."""
import sys,json,uuid
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from gie_runtime import Components,History,CurrentState
from load_balancer import EVSEState
from integracoes.weather.cache import ForecastCache
from observabilidade.run import run_observed_cycle
from observabilidade.log import DecisionLog

def execute(request):
    t=pd.Timestamp(request.get('decision_time') or pd.Timestamp.now(tz='America/Sao_Paulo').ceil('15min'))
    if t.tzinfo is not None:t=t.tz_convert('America/Sao_Paulo').tz_localize(None)
    source=pd.Timestamp('2026-06-15')+pd.Timedelta(days=t.dayofweek,hours=t.hour,minutes=t.minute)
    delta=t-source
    def history(name):
        raw=pd.read_csv(ROOT/'data'/name,parse_dates=['timestamp']).set_index('timestamp')
        current=raw.loc[source]
        frame=raw.loc[:source-pd.Timedelta(minutes=15)].tail(3000).copy();frame.index+=delta
        for k,v in dict(hora=frame.index.hour,dia_semana=frame.index.dayofweek,fim_de_semana=(frame.index.dayofweek>=5).astype(int),mes=frame.index.month).items():
            if k in frame:frame[k]=v
        return frame,current
    b,bc=history('consumo_predio_6_meses.csv');e,ec=history('demanda_carregadores_6_meses.csv')
    h=History(b,e,{'kind':'Live Demo: synthetic history replay with current weather','shift_days':delta.days,'live_plant':False})
    current=CurrentState(t,float(bc.consumo_predio_kw),float(ec.potencia_solicitada_kw),25.,50.,
        [EVSEState(f'EVSE{i}',True,connected_since=t-pd.Timedelta(hours=1)) for i in range(1,5)],
        provenance={'kind':'demonstration fixture; no physical equipment','solar_fixture_kw':25,'soc_fixture_pct':50})
    components=Components.real(ROOT)
    components.solar.cache=ForecastCache(ROOT/'outputs/observabilidade/live/.cache/last_weather.json')
    run_id=uuid.uuid4().hex
    result=run_observed_cycle(t,h,current,components,previous_trace=request.get('previous_trace'),
        logger=DecisionLog(ROOT/'outputs/observabilidade/live'/f'{run_id}.jsonl'))
    frame={'title':'Live Demo — componentes reais / telemetria simulada',
        'provenance':'No physical telemetry; model inference and weather query execute now.',
        'cycle':result,'trace':result['decision_trace']}
    path=ROOT/'outputs/observabilidade/live'/f'{run_id}.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(frame,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return path

if __name__=='__main__':
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    print(str(execute(request)),flush=True)
