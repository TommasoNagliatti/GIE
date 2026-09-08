"""One atomic simulated step through frozen run_gie_cycle; no control law here."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from gie_runtime import Components,run_gie_cycle
from load_balancer.state import BalancerState
from observabilidade.trace import build_trace
from .telemetry import Telemetry
from .state import timestamp
class Engine:
    def __init__(self,root,components=None):
        self.telemetry=Telemetry(root)
        if components is None:
            from motor_consumo.predict import MotorHibrido
            from motor_carregadores_v2.predict import MotorCarregadores
            components=Components(MotorHibrido(),MotorCarregadores(),self.telemetry.solar)
        self.components=components
    def step(self,state):
        if state["stopped"] or state["index"]>=state["total_steps"]:raise ValueError("Simulation stopped or complete")
        s=deepcopy(state);t=timestamp(s)
        current,br,er,flags=self.telemetry.sample(s)
        cycle=run_gie_cycle(t,self.telemetry.history(s),current,self.components,
            balancer_state=BalancerState(**s["balancer_state"]) if s["balancer_state"] else None)
        for kind in flags:
            if any(e["kind"]==kind and e["start"]==s["index"] for e in s["events"]):
                cycle["events"].append(dict(timestamp=str(t),code="SIMULATION_"+kind.upper(),severity="info",component="simulation",context={"telemetry_only":True}))
        trace=build_trace(cycle,s["previous_trace"])
        frame={"title":"Simulation Mode · "+str(t),"provenance":"Continuous synthetic state; frozen GIE components, no equipment commands","cycle":cycle,"trace":trace}
        s["last_frame"]=frame
        mg=cycle["management"]
        if not mg["execution_allowed"]:
            s["stopped"]=True;return s
        validate_cycle(cycle)
        s["soc"]=mg["battery_soc_after_pct"];s["previous_charge_kw"]=mg["battery_charge_kw"];s["previous_discharge_kw"]=mg["battery_discharge_kw"]
        s["balancer_state"]=cycle["load_balancer"]["next_state"];s["previous_trace"]=trace
        # Append only completed interval's observations. Never feed future disturbances.
        er["potencia_entregue_kw"]=mg["first_decision"]["ev_served_kw"];er["energia_entregue_kwh"]=er["potencia_entregue_kw"]*.25
        s["observations"].append({"timestamp":str(t),"building":{k:float(v) for k,v in br.items()},"ev":{k:float(v) for k,v in er.items()}})
        row=dict(timestamp=str(t),building_kw=current.building_kw,solar_kw=current.solar_kw,ev_demand_kw=current.ev_demand_kw,
                 soc_before_pct=current.battery_soc_pct,soc_after_pct=s["soc"],battery_charge_kw=mg["battery_charge_kw"],battery_discharge_kw=mg["battery_discharge_kw"],
                 grid_import_kw=mg["grid_import_plan_kw"],grid_export_kw=mg["grid_export_plan_kw"],ev_block_limit_kw=mg["ev_block_limit_kw"],
                 ev_served_kw=mg["first_decision"]["ev_served_kw"],ev_unserved_kw=mg["current_ev_unserved_total_kw"],
                 **{f"evse_{i}_kw":cycle["load_balancer"][f"evse_{i}_kw"] for i in range(1,5)},status=cycle["status"])
        s["rows"].append(row);s["index"]+=1
        return s

def validate_cycle(c):
    m=c["management"];p=m["physical_config"];lb=c["load_balancer"];tol=1e-5
    assert m["execution_allowed"]
    assert 20-tol<=m["battery_soc_after_pct"]<=95+tol
    for k,cap in [("battery_charge_kw",100),("battery_discharge_kw",100),("grid_import_plan_kw",350),("grid_export_plan_kw",150),("ev_block_limit_kw",88)]:
        assert -tol<=m[k]<=cap+tol,(k,m[k])
    assert min(m["battery_charge_kw"],m["battery_discharge_kw"])<=tol
    assert min(m["grid_import_plan_kw"],m["grid_export_plan_kw"])<=tol
    vals=[lb[f"evse_{i}_kw"] for i in range(1,5)]
    assert all(-tol<=v<=22+tol for v in vals) and sum(vals)<=m["ev_block_limit_kw"]+tol
    for i in range(1,5):
        if lb[f"EVSE{i}"]["state"]=="fault":assert lb[f"evse_{i}_kw"]==0
    soc=m["battery_soc_before_pct"]+(m["battery_charge_kw"]*p["charge_efficiency"]-m["battery_discharge_kw"]/p["discharge_efficiency"])*.25/p["battery_capacity_kwh"]*100
    assert abs(soc-m["battery_soc_after_pct"])<tol
    cur=c["current_state"];served=m["first_decision"]["ev_served_kw"]
    balance=cur["solar_kw"]+m["grid_import_plan_kw"]+m["battery_discharge_kw"]-cur["building_kw"]-served-m["battery_charge_kw"]-m["grid_export_plan_kw"]
    assert abs(balance)<tol
    assert m["battery_charge_kw"]<=max(0,cur["solar_kw"]-cur["building_kw"]-served)+tol
