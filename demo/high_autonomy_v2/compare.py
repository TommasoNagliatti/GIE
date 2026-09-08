import sys,json,math
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import numpy as np
import pandas as pd
from gie_runtime import Components,CurrentState,History
from load_balancer.state import EVSEState,BalancerState
from integracoes.solar.models import SolarForecast
from integracoes.weather.models import horizon
from motor_gerenciamento_v2.config import Config
from motor_gerenciamento_v2.runtime_adapter import run_cycle
from motor_gerenciamento.validation import validate_plan
from motor_gerenciamento.state import State
from observabilidade.trace import build_trace
from observabilidade.log import DecisionLog
from demo.simulation.telemetry import Telemetry

def metrics(frames):
    rows=[]
    for f in frames:
        c=f["cycle"];m=c["management"];cur=c["current_state"];row=m["first_decision"]
        rows.append(dict(timestamp=c["decision_time"],building_kw=cur["building_kw"],ev_demand_kw=cur["ev_demand_kw"],ev_served_kw=row["ev_served_kw"],solar_kw=cur["solar_kw"],grid_import_kw=m["grid_import_plan_kw"],grid_export_kw=m["grid_export_plan_kw"],battery_charge_kw=m["battery_charge_kw"],battery_discharge_kw=m["battery_discharge_kw"],soc_before_pct=cur["battery_soc_pct"],soc_after_pct=m["battery_soc_after_pct"],ev_unserved_kw=m["current_ev_unserved_total_kw"]))
    d=pd.DataFrame(rows)
    energy=lambda k:float(d[k].sum()*.25)
    total=energy("building_kw")+energy("ev_served_kw");solar=energy("solar_kw");export=energy("grid_export_kw")
    return d,dict(building_kwh=energy("building_kw"),ev_requested_kwh=energy("ev_demand_kw"),ev_served_kwh=energy("ev_served_kw"),total_consumed_kwh=total,
                  solar_generated_kwh=solar,solar_self_consumed_kwh=solar-export,solar_exported_kwh=export,grid_imported_kwh=energy("grid_import_kw"),
                  grid_peak_kw=float(d.grid_import_kw.max()),battery_charged_kwh=energy("battery_charge_kw"),battery_discharged_kwh=energy("battery_discharge_kw"),
                  soc_min_pct=float(min(d.soc_before_pct.min(),d.soc_after_pct.min())),soc_max_pct=float(max(d.soc_before_pct.max(),d.soc_after_pct.max())),soc_final_pct=float(d.soc_after_pct.iloc[-1]),
                  ev_unserved_kwh=energy("ev_unserved_kw"),solar_self_consumption_pct=100*(solar-export)/solar if solar else 0,
                  self_sufficiency_pct=100*(1-energy("grid_import_kw")/total),initial_stored_energy_kwh=50/100*(200 if frames[0]["cycle"]["motor3_version"]=="1.1" else 2000))
class Model:
    def __init__(self,data):self.data=data
    def predict(self,*a):return self.data.copy(deep=True)
class Solar:
    def __init__(self,data):self.data=data
    def forecast(self,t):return SolarForecast(self.data,"simulation_weather",False,{"simulation":True,"scaled_profile":"800kWp/500kW","same_irradiance_as_V1":True})
def run():
    out=ROOT/"outputs/high_autonomy_v2/comparison";out.mkdir(parents=True,exist_ok=True)
    if (out/"v2_cycles.json").exists():raise FileExistsError("Comparison already complete")
    originals=json.loads((ROOT/"outputs/simulation/v1/run_24h/simulation.json").read_text(encoding="utf-8"))["cycles"]
    cfg=Config();soc=50.;prev_ch=prev_dis=0.;bal=None;trace=None;frames=[]
    telemetry=Telemetry(ROOT)
    for i,old in enumerate(originals):
        c=old["cycle"];t=pd.Timestamp(c["decision_time"]);fore=pd.DataFrame(c["forecasts"]["records"]);ix=pd.to_datetime(fore.timestamp)
        a=pd.DataFrame({"timestamp_previsto":ix,"consumo_previsto_kw":fore.building_kw})
        b=fore.drop(columns=["timestamp","building_kw","solar_previsto_kw"]).copy();b.insert(0,"timestamp_previsto",ix)
        pv=np.minimum(500,fore.solar_previsto_kw.to_numpy()*800/150)
        sf=pd.DataFrame({"solar_previsto_kw":pv},index=horizon(t))
        cur=dict(c["current_state"]);old_pv=cur["solar_kw"];reference=float(fore.solar_previsto_kw.iloc[0])
        cur["solar_kw"]=float(pv[0]*old_pv/reference) if reference>0 else 0.
        cur["battery_soc_pct"]=soc;cur["previous_charge_kw"]=prev_ch;cur["previous_discharge_kw"]=prev_dis
        cur["evses"]=[EVSEState(**d) for d in cur["evses"]]
        h=History(telemetry.building.loc[:t-pd.Timedelta(minutes=15)].tail(3000),telemetry.ev.loc[:t-pd.Timedelta(minutes=15)].tail(3000),
                  {"comparison":"Identical saved frozen model predictions; no retraining or forecast feedback change"})
        new=run_cycle(t,h,CurrentState(**cur),Components(Model(a),Model(b),Solar(sf)),config=cfg,balancer_state=bal)
        if not new["management"]["execution_allowed"]:
            (out/"failure.json").write_text(json.dumps(new,indent=2),encoding="utf-8");raise RuntimeError(new["health"])
        m=new["management"]
        validate_plan(m["plan"],State(soc,prev_ch,prev_dis),cfg)
        assert abs(m["power_balance_error_kw"])<1e-5
        assert m["battery_charge_kw"]<=max(0,cur["solar_kw"]-cur["building_kw"]-m["dispatchable_ev_demand_kw"])+1e-5
        new["events"].extend(e for e in c["events"] if e["code"].startswith("SIMULATION_"))
        trace=build_trace(new,trace);frames.append({"cycle":new,"trace":trace})
        DecisionLog(out/"events.jsonl").append(trace)
        soc=m["battery_soc_after_pct"]
        if abs(soc-20)<1e-8:soc=20.
        if abs(soc-95)<1e-8:soc=95.
        prev_ch=m["battery_charge_kw"];prev_dis=m["battery_discharge_kw"];bal=BalancerState(**new["load_balancer"]["next_state"])
        print(i+1,round(soc,3),round(m["grid_import_plan_kw"],3),flush=True)
    d1,s1=metrics(originals);d2,s2=metrics(frames)
    d1.to_csv(out/"v1_reference.csv",index=False);d2.to_csv(out/"v2.csv",index=False)
    (out/"v2_cycles.json").write_text(json.dumps(frames,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    (out/"metrics.json").write_text(json.dumps({"V1":s1,"V2":s2},indent=2),encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(3,1,figsize=(13,10),sharex=True);times=pd.to_datetime(d2.timestamp)
    ax[0].plot(times,d1.grid_import_kw,label="Rede V1");ax[0].plot(times,d2.grid_import_kw,label="Rede V2");ax[0].plot(times,d2.solar_kw,label="Solar V2");ax[0].set_ylabel("kW");ax[0].legend()
    ax[1].plot(times,d2.battery_charge_kw,label="Carga V2");ax[1].plot(times,d2.battery_discharge_kw,label="Descarga V2");ax[1].set_ylabel("kW");ax[1].legend()
    ax[2].plot(times,d1.soc_after_pct,label="SOC V1");ax[2].plot(times,d2.soc_after_pct,label="SOC V2");ax[2].axhline(20,color="red",ls="--");ax[2].set_ylabel("SOC %");ax[2].legend()
    fig.autofmt_xdate();fig.tight_layout();fig.savefig(out/"comparison.png",dpi=140)
if __name__=="__main__":run()
