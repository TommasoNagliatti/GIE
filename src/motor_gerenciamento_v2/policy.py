"""Lexicographic LP using the frozen Motor 3 constraints, parser and physical guard."""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import vstack,csr_matrix
from motor_gerenciamento.constraints import Layout
from motor_gerenciamento.run import run_control as v1_run_control
from .config import Config

def lex_solver(ignored_cost,**kwargs):
    """Objectives fixed in priority order, not weighted tariffs or wear penalties."""
    l=Layout(48);n=l.size
    stages=[]
    for name,current in [("ev_unserved_kw",False),("grid_import_kw",False),("grid_import_kw",True),("grid_export_kw",False),("grid_export_kw",True)]:
        v=np.zeros(n)
        for t in ([0] if current else range(48)):v[l.at(name,t)]=.25
        stages.append(v)
    tie=np.zeros(n)
    for t in range(48):
        tie[l.at("battery_charge_kw",t)]=.25;tie[l.at("battery_discharge_kw",t)]=.25
    stages.append(tie) # Only among identical EV/import/export optima; cannot save battery at their expense.
    head=np.zeros(n)
    for t in range(48):head[l.at("ev_q90_headroom_shortfall_kw",t)]=1
    stages.append(head)
    problem=dict(kwargs);problem["bounds"]=list(problem["bounds"])
    # Compatibility variable retained at zero; no reserve constraint can bind.
    for t in range(48):problem["bounds"][l.at("reserve_deficit_kwh",t)]=(0,0)
    audit=[]
    for v in stages:
        result=linprog(v,**problem)
        if not result.success:raise RuntimeError(result.message)
        optimum=float(v@result.x);audit.append(optimum)
        problem["A_ub"]=vstack([problem["A_ub"],csr_matrix(v.reshape(1,-1))],format="csr")
        problem["b_ub"]=np.append(problem["b_ub"],optimum+1e-7)
    result.fun=float(stages[1]@result.x)
    result.lexicographic_optima=audit
    return result

def run_control(building_forecast,ev_forecast,solar_forecast,import_tariff=None,export_credit=None,state=None,measurements=None,config=None,execution_measurements=None,solver=None):
    c=config or Config();a=building_forecast.copy(deep=True);b=ev_forecast.copy(deep=True);pv=solar_forecast.copy(deep=True)
    # Current real measurements participate in the MPC, not only its projection.
    if execution_measurements is not None:
        m=execution_measurements
        a.loc[a.index[0],"consumo_previsto_kw"]=m.building_kw
        b.loc[b.index[0],"potencia_solicitada_prevista_kw"]=m.ev_kw
        b.loc[b.index[0],"potencia_solicitada_alta_kw"]=max(m.ev_kw,float(b.potencia_solicitada_alta_kw.iloc[0]))
        pv.iloc[0]=m.solar_kw
    result=v1_run_control(a,b,pv,state=state,measurements=measurements,config=c,execution_measurements=execution_measurements,solver=solver or lex_solver)
    # Do not silently deploy a V1 fallback as a V2 policy.
    if result.get("fallback_used"):raise RuntimeError("V2 LP unavailable; revision stops: "+str(result.get("fallback_reason")))
    result["policy_revision"]="high_autonomy_v2"
    result["objective_policy"]="lexicographic_EV_service_import_kWh_current_import_export_current_export_degeneracy_headroom"
    return result
