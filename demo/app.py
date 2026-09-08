"""Optional read-only dashboard; core runs in its own Python process."""
import sys,json,time,subprocess,uuid,os
from pathlib import Path
from datetime import datetime,timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import streamlit as st
import pandas as pd
from demo.session import ReplaySession,LiveGate
from demo.visuals import energy_svg
st.set_page_config(page_title="GIE | Observabilidade",page_icon="⚡",layout="wide")
st.markdown("<style>.stApp{background:#081425;color:#edf5fc}section[data-testid=stSidebar]{background:#102338}div[data-testid=stMetric]{background:#13283e;padding:14px;border-radius:12px}h1,h2,h3{color:#edf5fc}div[data-testid=stMetricValue]{font-size:20px}</style>",unsafe_allow_html=True)
if "replay" not in st.session_state:
    st.session_state.replay=ReplaySession(ROOT/"outputs/observabilidade/v1/replay_cycles.jsonl")
    st.session_state.gate=LiveGate()
    st.session_state.live_frame=None
    st.session_state.live_playing=False
st.sidebar.title("⚡ GIE")
st.sidebar.caption("GERENCIAMENTO INTELIGENTE DE ENERGIA")
mode=st.sidebar.radio("Modo",["Replay","Live Demo","Simulation Mode"])
delay=8
if mode!="Simulation Mode":
    delay=st.sidebar.slider("Auto Play · segundos",3,30,8)
    st.sidebar.info("Replay: 8 cenários salvos, sem internet. Os cenários são independentes; não representam uma trajetória contínua de SOC.")
    st.sidebar.caption("Live Demo: modelos reais e consulta meteorológica; histórico e medições simulados. Nenhum equipamento é comandado. Intervalo mínimo entre execuções: 30 s.")
    st.sidebar.markdown("**Instalação V1**\n\n4 EVSEs × 22 kW\n\nBateria 200 kWh · ±100 kW\n\nRede máxima 350 kW")

if mode=="Simulation Mode":
    st.session_state.replay.playing=False
    st.session_state.live_playing=False
    from demo.simulation.ui import render
    render()
    st.stop()
if "sim_clock" in st.session_state:st.session_state.sim_clock.pause()

def live():
    gate=st.session_state.gate
    if gate.count>=48:
        st.warning("Limite de 48 ciclos nesta sessão atingido.");return
    if not gate.begin(time.monotonic()):
        st.info("Aguarde 30 segundos entre ciclos Live.");return
    try:
        previous=st.session_state.live_frame
        request={}
        if previous:
            request["previous_trace"]=previous["trace"]
            request["decision_time"]=(datetime.fromisoformat(previous["cycle"]["decision_time"])+timedelta(minutes=15)).isoformat()
        folder=ROOT/"outputs/observabilidade/live";folder.mkdir(parents=True,exist_ok=True)
        path=folder/(uuid.uuid4().hex+"_request.json")
        path.write_text(json.dumps(request),encoding="utf-8")
        with st.spinner("Executando os componentes existentes…"):
            p=subprocess.run([str(ROOT/".venv/Scripts/python.exe"),"-B",str(ROOT/"demo/live_worker.py"),str(path)],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=90,env={**os.environ,"PYTHONIOENCODING":"utf-8"})
        if p.returncode:raise RuntimeError(p.stderr[-2500:])
        st.session_state.live_frame=json.loads(Path(p.stdout.strip().splitlines()[-1]).read_text(encoding="utf-8"))
    except Exception as e:
        st.error(str(e));st.session_state.live_playing=False
    finally:gate.end()

@st.fragment(run_every="1s" if st.session_state.replay.playing or st.session_state.live_playing else None)
def dashboard():
    replay=st.session_state.replay
    st.caption("VISIBILIDADE OPERACIONAL · V1")
    st.title("Cada decisão, com evidência.")
    a,b,c=st.columns([2,2,6])
    nxt=a.button("Próximo intervalo",key="next")
    auto=b.button("Auto Play / Pausar",key="auto")
    reset=c.button("Reset",key="reset")
    if mode=="Replay":
        st.session_state.live_playing=False
        if reset:replay.reset()
        if auto:replay.playing=not replay.playing;replay.last_advance=time.monotonic();st.rerun()
        if nxt:replay.advance(time.monotonic())
        replay.advance(time.monotonic(),automatic=True,delay=delay)
        frame=replay.current()
        st.caption(f"Intervalo ilustrativo {replay.index+1}/{len(replay.frames)} · Auto Play {'ativo' if replay.playing else 'pausado'}")
    else:
        replay.playing=False
        if reset:st.session_state.live_frame=None;st.session_state.live_playing=False
        if auto:st.session_state.live_playing=not st.session_state.live_playing;st.rerun()
        gate=st.session_state.gate
        if nxt or (st.session_state.live_playing and (gate.last_request is None or time.monotonic()-gate.last_request>=30)):live()
        frame=st.session_state.live_frame
        if frame is None:st.info("Clique em Próximo intervalo para executar um ciclo Live Demo.");return
    cycle=frame["cycle"];trace=frame["trace"];cur=cycle.get("current_state") or {};mg=cycle.get("management") or {}
    st.subheader(frame["title"])
    st.caption(f'{cycle["decision_time"]} · Status: {cycle["status"]} · {frame.get("provenance","")}')
    values=[("Prédio",cur.get("building_kw"),"kW"),("Solar",cur.get("solar_kw"),"kW"),("SOC",cur.get("battery_soc_pct"),"%"),("Bateria carga",mg.get("battery_charge_kw"),"kW"),("Importação",mg.get("grid_import_plan_kw"),"kW"),("Bloco EV",mg.get("ev_block_limit_kw"),"kW")]
    for col,(label,value,unit) in zip(st.columns(6),values):col.metric(label,"—" if value is None else f"{value:.2f} {unit}")
    st.image(energy_svg(cycle),width="stretch")
    lb=cycle.get("load_balancer") or {}
    for i,col in enumerate(st.columns(4),1):
        entry=lb.get(f"EVSE{i}",{})
        col.metric(f"EVSE {i}",f'{lb.get(f"evse_{i}_kw",0):.2f} kW' if lb else "Sem comando")
        col.caption(str(entry.get("state","")))
    st.caption(f'Descarga bateria: {mg.get("battery_discharge_kw","—")} kW · Exportação: {mg.get("grid_export_plan_kw","—")} kW · SOC após passo: {mg.get("battery_soc_after_pct","—")}% · Setpoints são limites, não consumo medido.')
    forecast,decisions,health,context=st.tabs(["Previsões · 12h","Decisões e eventos","Health","Contexto opcional"])
    with forecast:
        records=(cycle.get("forecasts") or {}).get("records",[])
        if records:
            df=pd.DataFrame(records)
            st.caption("Previsões dos componentes existentes; Q90 é margem de planejamento.")
            timecol=next((k for k in df if "timestamp" in k),None)
            if timecol:df=df.set_index(timecol)
            power=[k for k in df if k.endswith("_kw")]
            if power:st.line_chart(df[power])
            other=[k for k in df if "fila" in k or "ocup" in k]
            if other:st.line_chart(df[other])
        else:st.warning("Previsões indisponíveis neste ciclo.")
    with decisions:
        rows=[{k:(str(d[k]) if k in ("previous_value","new_value") else d[k]) for k in ("action","component","previous_value","new_value","changed","reason_codes")} for d in trace["decisions"]]
        st.dataframe(rows,width="stretch")
        events=trace["events"]
        if mode=="Replay":events=[e for f in replay.frames[max(0,replay.index-2):replay.index+1] for e in f["trace"]["events"]]
        st.dataframe([{k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v)) for k,v in e.items()} for e in events[-30:]],width="stretch")
        st.download_button("Baixar Decision Trace",json.dumps(trace,ensure_ascii=False,indent=2),file_name="decision_trace.json",mime="application/json")
        if trace.get("logging_error"):st.error(trace["logging_error"])
    with health:st.json(trace["health"])
    with context:
        st.caption("Payload determinístico e compacto. Nenhuma chamada a LLM.")
        st.json(trace.get("llm_context",{}))
dashboard()
