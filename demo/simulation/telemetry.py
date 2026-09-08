"""Synthetic telemetry and weather fixture; official datasets are read-only."""
import math
import pandas as pd
from pathlib import Path
from gie_runtime import CurrentState,History
from load_balancer import EVSEState
from integracoes.weather.models import horizon
from integracoes.solar.models import SolarForecast
from integracoes.solar.config import SolarConfig
from integracoes.solar.forecast import irradiance_to_power
from .state import timestamp
from .scenarios import active

class SimulatedSolar:
    """Declared clear-day irradiance fixture; uses existing PV conversion unchanged."""
    def forecast(self,t):
        ix=horizon(t)
        irradiance=[900*max(0,math.sin(math.pi*((x.hour+x.minute/60)-6)/12))**1.4 if 6<=x.hour+x.minute/60<=18 else 0 for x in ix]
        frame=pd.DataFrame({"global_tilted_irradiance_wm2":irradiance},index=ix)
        frame["solar_previsto_kw"]=irradiance_to_power(frame.global_tilted_irradiance_wm2,SolarConfig())
        return SolarForecast(frame,"simulation_weather",False,{"simulation":True,"diagnostics":["Synthetic clear-day irradiance; not current Open-Meteo or an accuracy evaluation."],"peak_irradiance_wm2":900,"sunrise_hour":6,"sunset_hour":18})
    def measured(self,t):
        # Deterministic modest cloud variation, not a change to PV parameters.
        factor=.92+.06*math.sin(pd.Timestamp(t).value/1e9/3600*1.7)
        return float(self.forecast(t).data.solar_previsto_kw.iloc[0])*factor

class Telemetry:
    def __init__(self,root):
        self.building=pd.read_csv(Path(root)/"data/consumo_predio_6_meses.csv",parse_dates=["timestamp"]).set_index("timestamp")
        self.ev=pd.read_csv(Path(root)/"data/demanda_carregadores_6_meses.csv",parse_dates=["timestamp"]).set_index("timestamp")
        self.solar=SimulatedSolar()
    def sample(self,state):
        t=pd.Timestamp(timestamp(state));flags=active(state)
        br=self.building.loc[t].copy();er=self.ev.loc[t].copy()
        b=float(br.consumo_predio_kw);ev=float(er.potencia_solicitada_kw);pv=self.solar.measured(t)
        n=min(4,max(int(er.carros_conectados),math.ceil(ev/22)))
        if "building_peak" in flags:b+=160.
        if "ev_peak" in flags:
            ev=88.;n=4;er["carros_chegando"]=max(float(er.carros_chegando),6) if any(e["kind"]=="ev_peak" and e["start"]==state["index"] for e in state["events"]) else er.carros_chegando
        if "solar_drop" in flags:pv*=.15
        devices=[]
        for i in range(1,5):
            key=f"EVSE{i}";connected=i<=n
            if connected and not state["connected_since"].get(key):state["connected_since"][key]=str(t)
            if not connected:state["connected_since"][key]=None
            devices.append(EVSEState(key,connected,"fault" if f"fault_{i}" in flags else "available",connected_since=state["connected_since"].get(key)))
        br["consumo_predio_kw"]=b;br["consumo_predio_kwh"]=b*.25
        er["potencia_solicitada_kw"]=ev;er["carros_conectados"]=n;er["carregadores_ocupados"]=n;er["ocupacao_pct"]=n/4*100
        current=CurrentState(t,b,ev,pv,state["soc"],devices,state["previous_charge_kw"],state["previous_discharge_kw"],
            {"simulation":True,"telemetry_source":"official profile with demonstration disturbances","active_disturbances":flags})
        return current,br,er,flags
    def history(self,state):
        origin=pd.Timestamp(timestamp(state))-pd.Timedelta(minutes=15)
        b=self.building.loc[:origin].tail(3000).copy();e=self.ev.loc[:origin].tail(3000).copy()
        if len(b)<2689 or len(e)<2689:raise ValueError("Insufficient historical context; use June 2026")
        for obs in state["observations"]:
            t=pd.Timestamp(obs["timestamp"])
            if t in b.index:
                for k,v in obs["building"].items():b.loc[t,k]=v
            if t in e.index:
                for k,v in obs["ev"].items():e.loc[t,k]=v
        return History(b,e,{"simulation":True,"observed_history_only":True,"source":"official CSV plus completed simulated measurements"})
