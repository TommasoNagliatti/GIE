"""Create offline demonstration recordings, without changing any frozen module."""
import sys,json,io,hashlib,socket
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from gie_runtime import Components,History,CurrentState,run_gie_cycle
from motor_consumo.predict import MotorHibrido
from motor_carregadores_v2.predict import MotorCarregadores
from integracoes.weather.open_meteo import OpenMeteoProvider
from integracoes.weather.models import WeatherSite,horizon
from integracoes.solar.models import SolarForecast
from integracoes.solar.forecast import irradiance_to_power
from integracoes.solar.config import SolarConfig
from load_balancer import EVSEState
from observabilidade.trace import build_trace
from observabilidade.log import DecisionLog

class RecordedSolar:
    def __init__(self):
        self.reference=json.loads((ROOT/'outputs/gie_runtime/v1/cycle.json').read_text(encoding='utf-8'))
        raw=json.loads((ROOT/'outputs/gie_runtime/v1/weather_raw.json').read_text(encoding='utf-8'))
        start=pd.Timestamp(self.reference['decision_time'])
        provider=OpenMeteoProvider(transport=lambda url,timeout:raw,clock=lambda:pd.Timestamp(start,tz='America/Sao_Paulo'))
        self.batch=provider.fetch(start,WeatherSite(),96)
    def forecast(self,start):
        data=self.batch.select(horizon(start))
        data['solar_previsto_kw']=irradiance_to_power(data.global_tilted_irradiance_wm2,SolarConfig())
        return SolarForecast(data,'recorded_open_meteo',True,{'diagnostics':['Offline replay of saved forecast; not a fresh weather query.'],'recorded':True})

def prepare():
    out=ROOT/'outputs/observabilidade/v1';path=out/'replay_cycles.jsonl'
    if path.exists():raise FileExistsError('Replay already recorded; no silent overwrite.')
    original=json.loads((ROOT/'outputs/gie_runtime/v1/cycle.json').read_text(encoding='utf-8'))
    start=pd.Timestamp(original['decision_time']);delta=pd.Timedelta(days=84)
    raw_b=pd.read_csv(ROOT/'data/consumo_predio_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
    raw_e=pd.read_csv(ROOT/'data/demanda_carregadores_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
    components=Components(MotorHibrido(),MotorCarregadores(),RecordedSolar())
    scenarios=[('Operação registrada',None),('Excedente solar',dict(b=35,ev=12,pv=125,soc=50)),
        ('Pico de demanda',dict(b=310,ev=60,pv=5,soc=60)),('EV acima da previsão',dict(b=160,ev=80,pv=15,soc=55)),
        ('Falha no EVSE3',dict(b=170,ev=80,pv=0,soc=50,fault=True)),('Bateria no mínimo',dict(b=300,ev=80,pv=0,soc=20)),
        ('Exportação solar',dict(b=25,ev=10,pv=125,soc=95)),('Execução bloqueada',dict(b=500,ev=44,pv=0,soc=20))]
    frames=[];previous=None;logger=DecisionLog(out/'events_decisions.jsonl')
    for i,(title,v) in enumerate(scenarios):
        t=start+i*pd.Timedelta(minutes=15)
        if v is None:cycle=original
        else:
            def replay(raw):
                frame=raw.loc[:t-delta-pd.Timedelta(minutes=15)].tail(3000).copy();frame.index+=delta
                for key,val in dict(hora=frame.index.hour,dia_semana=frame.index.dayofweek,fim_de_semana=(frame.index.dayofweek>=5).astype(int),mes=frame.index.month).items():
                    if key in frame:frame[key]=val
                return frame
            history=History(replay(raw_b),replay(raw_e),{'kind':'offline synthetic historical replay','shift_days':84})
            devices=[EVSEState(f'EVSE{k}',True,'fault' if k==3 and v.get('fault') else 'available',connected_since=t-pd.Timedelta(hours=1)) for k in range(1,5)]
            current=CurrentState(t,v['b'],v['ev'],v['pv'],v['soc'],devices,
                previous_charge_kw=(frames[-1]['cycle'].get('management') or {}).get('battery_charge_kw',0),
                previous_discharge_kw=(frames[-1]['cycle'].get('management') or {}).get('battery_discharge_kw',0),
                provenance={'kind':'independent illustrative telemetry fixture','continuous_physical_simulation':False,'scenario':title})
            cycle=run_gie_cycle(t,history,current,components)
        trace=build_trace(cycle,previous);logger.append(trace);previous=trace
        frames.append({'title':title,'provenance':'Recorded E2E cycle' if i==0 else 'Independent illustrative fixture, not continuous plant telemetry','cycle':cycle,'trace':trace})
        print(title,cycle['status'],flush=True)
    path.write_text(''.join(json.dumps(f,ensure_ascii=False,allow_nan=False)+chr(10) for f in frames),encoding='utf-8')
    (out/'decision_trace_example.json').write_text(json.dumps(frames[1]['trace'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'llm_context_example.json').write_text(json.dumps(frames[1]['trace']['llm_context'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'replay_manifest.json').write_text(json.dumps({'frames':len(frames),'offline':True,'fixture_scenarios':True,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':
    def forbidden(*args,**kwargs):raise RuntimeError('Network forbidden while preparing offline replay.')
    socket.socket=forbidden
    prepare()
