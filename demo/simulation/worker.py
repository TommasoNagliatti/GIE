"""Core-environment worker. UI never imports numerical core dependencies."""
import sys,json,argparse,uuid,os
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from demo.simulation.engine import Engine
from demo.simulation.state import initial
from demo.simulation.scenarios import inject,VALIDATION_EVENTS
from observabilidade.log import DecisionLog

def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding="utf-8");os.replace(tmp,path)
def save_step(folder,state):
    frame=state["last_frame"]
    atomic_json(folder/"state.json",state)
    suffix="_blocked" if state["stopped"] else ""
    atomic_json(folder/f"cycle_{len(state['rows']):03d}{suffix}.json",frame)
    DecisionLog(folder/"events.jsonl").append(frame["trace"])
def batch(folder,hours=24,start="2026-06-15 00:00:00"):
    folder=Path(folder)
    if (folder/"state.json").exists():raise FileExistsError("Use a new output directory")
    e=Engine(ROOT);s=initial(start,hours)
    for i in range(s["total_steps"]):
        if i in VALIDATION_EVENTS:inject(s,VALIDATION_EVENTS[i])
        s=e.step(s);save_step(folder,s)
        print(f"step={s['index']} SOC={s['soc']:.2f} status={s['last_frame']['cycle']['status']}",flush=True)
        if s["stopped"]:raise RuntimeError("Blocked cycle; stopped without advancing SOC")
    import pandas as pd
    df=pd.DataFrame(s["rows"]);df.to_csv(folder/"simulation.csv",index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(12,9),sharex=True)
    t=pd.to_datetime(df.timestamp)
    for k in ["building_kw","solar_kw","ev_demand_kw","grid_import_kw"]:axes[0].plot(t,df[k],label=k)
    axes[0].axhline(300,color="red",ls="--",label="Alvo rede");axes[0].set_ylabel("kW");axes[0].legend(ncol=3)
    for k in ["battery_charge_kw","battery_discharge_kw","grid_export_kw"]:axes[1].plot(t,df[k],label=k)
    axes[1].set_ylabel("kW");axes[1].legend()
    axes[2].plot(t,df.soc_before_pct,label="SOC antes");axes[2].plot(t,df.soc_after_pct,label="SOC após");axes[2].set_ylabel("SOC %");axes[2].legend()
    fig.suptitle("GIE · 24h simuladas · decisões dos componentes congelados");fig.autofmt_xdate();fig.tight_layout();fig.savefig(folder/"simulation.png",dpi=140);plt.close(fig)
    frames=[json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("cycle_*.json"))]
    atomic_json(folder/"simulation.json",{"metadata":{"simulation":True,"start":start,"hours":hours,"steps":len(df),"network":False,"predeclared_events":VALIDATION_EVENTS,"solar":"Synthetic irradiance fixture, existing solar conversion","note":"Fast batch without wall-clock pacing; same Engine.step used by UI"},"cycles":frames})
    atomic_json(folder/"summary.json",{"cycles":len(df),"hours":len(df)*.25,"soc_initial":s["initial_soc"],"soc_final":s["soc"],"max_grid_kw":df.grid_import_kw.max(),"max_block_kw":df.ev_block_limit_kw.max(),"ev_unserved_kwh":df.ev_unserved_kw.sum()*.25,"physical_checks_passed":True})
    return s

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--batch");p.add_argument("--request");a=p.parse_args()
    if a.batch:batch(a.batch)
    else:
        req=json.loads(Path(a.request).read_text(encoding="utf-8"));folder=Path(req["folder"]).resolve()
        allowed=(ROOT/"outputs/simulation").resolve()
        if not folder.is_relative_to(allowed):raise ValueError("Output must be under outputs/simulation")
        statefile=folder/"state.json"
        s=json.loads(statefile.read_text(encoding="utf-8")) if statefile.exists() else initial(req["start"],req["hours"])
        for kind in req.get("inject",[]):inject(s,kind,req.get("duration",4))
        s=Engine(ROOT).step(s);save_step(folder,s)
        print(str(statefile),flush=True)
