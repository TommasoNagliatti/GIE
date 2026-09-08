"""Streamlit-only simulation controller. Numerical execution stays in core venv."""
import json,subprocess,uuid,time,os
from pathlib import Path
from datetime import date,datetime,timedelta
import streamlit as st
import pandas as pd
from .state import Playback,SPEEDS
from .scenarios import LABELS
from .view import diagram,timeline
ROOT=Path(__file__).resolve().parents[2]
def render():
    if "sim_clock" not in st.session_state:
        st.session_state.sim_clock=Playback()
        st.session_state.sim_state=None
        st.session_state.sim_folder=str(ROOT/"outputs/simulation/sessions"/uuid.uuid4().hex)
        st.session_state.sim_pending=[]
        st.session_state.sim_error=None
    clock=st.session_state.sim_clock;state=st.session_state.sim_state
    started=bool(state and (state["index"] or state["stopped"]))
    st.sidebar.subheader("Simulation Mode")
    day=st.sidebar.date_input("Dia inicial",date(2026,6,15),min_value=date(2026,6,1),max_value=date(2026,6,28),disabled=started)
    hours=st.sidebar.slider("Duração simulada · horas",1,48,24,disabled=started)
    speed=st.sidebar.selectbox("Velocidade",list(SPEEDS),index=1)
    if clock.interval!=SPEEDS[speed]:clock.speed(SPEEDS[speed],time.monotonic())
    st.sidebar.caption("1 passo = 15 min. Eventos alteram somente telemetria. Falhas expiram após a duração escolhida.")
    selected=st.sidebar.multiselect("Eventos para o próximo passo",list(LABELS),format_func=lambda k:LABELS[k])
    duration=st.sidebar.slider("Duração do evento · passos",1,16,4)
    if st.sidebar.button("Agendar eventos"):
        st.session_state.sim_pending=[{"kind":k,"duration":duration} for k in selected]
    if st.session_state.sim_pending:st.sidebar.info("Agendado: "+", ".join(LABELS[e["kind"]] for e in st.session_state.sim_pending))
    saved=ROOT/"outputs/simulation/v1/run_24h/state.json"
    if (saved.parent/"summary.json").exists() and st.sidebar.button("Abrir execução de 24h salva"):
        clock.pause();st.session_state.sim_state=json.loads(saved.read_text(encoding="utf-8"))
        st.session_state.sim_folder=str(saved.parent);st.session_state.sim_pending=[];st.rerun()

    def step():
        began=time.monotonic()
        folder=Path(st.session_state.sim_folder);folder.mkdir(parents=True,exist_ok=True)
        pending=st.session_state.sim_pending
        # One common duration is selected per injection batch.
        request={"folder":str(folder),"start":str(day)+" 00:00:00","hours":hours,
                 "inject":[e["kind"] for e in pending],"duration":pending[0]["duration"] if pending else 4}
        req=folder/("request_"+uuid.uuid4().hex+".json")
        req.write_text(json.dumps(request),encoding="utf-8")
        try:
            with st.spinner("GIE executando um passo de 15 minutos…"):
                p=subprocess.run([str(ROOT/".venv/Scripts/python.exe"),"-B",str(ROOT/"demo/simulation/worker.py"),"--request",str(req)],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=90,env={**os.environ,"PYTHONIOENCODING":"utf-8"})
            if p.returncode:raise RuntimeError(p.stderr[-2500:])
            st.session_state.sim_state=json.loads((folder/"state.json").read_text(encoding="utf-8"))
            st.session_state.sim_pending=[];st.session_state.sim_error=None
            s=st.session_state.sim_state
            if s["stopped"] or s["index"]>=s["total_steps"]:clock.pause()
        except Exception as e:
            st.session_state.sim_error=str(e);clock.pause()
        finally:clock.completed(began,time.monotonic())

    @st.fragment(run_every="1s" if clock.playing else None)
    def panel():
        st.caption("SIMULAÇÃO VISUAL · COMPONENTES GIE CONGELADOS")
        st.title("Um dia de energia, passo a passo.")
        a,b,c,d=st.columns(4)
        start=a.button("Iniciar",key="sim_start")
        pause=b.button("Pausar",key="sim_pause")
        nxt=c.button("Próximo passo",key="sim_next")
        reset=d.button("Reiniciar",key="sim_reset")
        if reset:
            clock.reset();st.session_state.sim_state=None;st.session_state.sim_folder=str(ROOT/"outputs/simulation/sessions"/uuid.uuid4().hex)
            st.session_state.sim_pending=[];st.session_state.sim_error=None;st.rerun()
        s=st.session_state.sim_state
        done=bool(s and (s["stopped"] or s["index"]>=s["total_steps"]))
        if pause:clock.pause();st.rerun()
        if start and not done:clock.start(time.monotonic());st.rerun()
        if not done and (nxt or clock.due(time.monotonic())):
            was_playing=clock.playing
            step()
            if was_playing and not clock.playing:st.rerun()
        s=st.session_state.sim_state
        if st.session_state.sim_error:st.error(st.session_state.sim_error)
        st.caption(f"{'Em execução' if clock.playing else 'Pausado'} · {speed} · um ciclo a cada ~{clock.interval:g} s; sem acumular passos atrasados.")
        if not s:
            st.info("Inicie ou avance um passo. Perfis oficiais do prédio/EV; clima sintético de demonstração. SOC inicial 50%. Nenhuma conexão com equipamentos.")
            return
        frame=s["last_frame"];shown=s["index"]
        if s["index"]==s["total_steps"]:
            shown=st.slider("Consultar ciclo concluído",1,s["total_steps"],s["total_steps"])
            frame=json.loads((Path(st.session_state.sim_folder)/f"cycle_{shown:03d}.json").read_text(encoding="utf-8"))
        cycle=frame["cycle"];m=cycle["management"];cur=cycle["current_state"]
        st.subheader(f'{cycle["decision_time"]} · {shown}/{s["total_steps"]} ciclos')
        st.progress(min(1,s["index"]/s["total_steps"]))
        st.caption("Telemetria simulada · solar 150 kWp / 125 kW AC · bateria 200 kWh · relógio local São Paulo")
        if s["stopped"]:st.error("Ciclo bloqueado. SOC não avançou. Consulte health e reinicie após revisar o cenário.")
        for col,(label,value) in zip(st.columns(4),[("Prédio · kW",cur["building_kw"]),("Solar · kW",cur["solar_kw"]),("EV demanda · kW",cur["ev_demand_kw"]),("SOC após · %",m.get("battery_soc_after_pct",s["soc"]))]):col.metric(label,f"{value:.2f}")
        flags=[]
        if m.get("battery_charge_kw",0)>1e-5:flags.append("🟢 Bateria carregando")
        if m.get("battery_discharge_kw",0)>1e-5:flags.append("🟠 Bateria descarregando")
        if m.get("grid_export_plan_kw",0)>1e-5:flags.append("🔵 Exportação")
        if m.get("grid_import_plan_kw",0)>300+1e-5:flags.append("🔴 Rede acima do alvo")
        if m.get("current_ev_unserved_total_kw",0)>1e-5:flags.append("🟠 EV limitado")
        flags += ["🔴 "+d["evse_id"]+" em falha" for d in cur["evses"] if d["state"]=="fault"]
        if flags:st.warning(" · ".join(flags))
        st.image(diagram(cycle),width="stretch")
        st.caption("Setas contínuas: fluxo realizado calculado pelo runtime. Setas tracejadas: limites enviados aos EVSEs; não são medição individual.")
        for col,key,label in zip(st.columns(4),["battery_charge_kw","battery_discharge_kw","grid_import_plan_kw","grid_export_plan_kw"],["Carga bateria","Descarga bateria","Importação","Exportação"]):
            v=m.get(key);col.metric(label,"—" if v is None else f"{v:.2f} kW")
        history,forecasts,events,health=st.tabs(["Histórico acumulado","Previsões · 48 passos","Timeline de decisões","Health"])
        with history:
            if s["rows"]:
                df=pd.DataFrame(s["rows"][:shown]);df["timestamp"]=pd.to_datetime(df.timestamp);df=df.set_index("timestamp")
                st.line_chart(df[["building_kw","solar_kw","ev_demand_kw","grid_import_kw","grid_export_kw"]])
                st.line_chart(df[["battery_charge_kw","battery_discharge_kw"]])
                st.line_chart(df[["soc_before_pct","soc_after_pct"]])
                st.download_button("Baixar CSV acumulado",df.to_csv(),file_name="simulation.csv")
        with forecasts:
            records=(cycle.get("forecasts") or {}).get("records",[])
            if records:
                f=pd.DataFrame(records);f["timestamp"]=pd.to_datetime(f.timestamp);f=f.set_index("timestamp")
                st.line_chart(f[["building_kw","solar_previsto_kw","potencia_solicitada_prevista_kw","potencia_solicitada_alta_kw"]])
                st.line_chart(f[["carregadores_ocupados_previstos","probabilidade_fila"]])
            else:st.warning("Previsões indisponíveis")
        with events:
            folder=Path(st.session_state.sim_folder)
            frames=[json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("cycle_*.json"))[:shown][-4:]]
            st.dataframe(timeline(frames),width="stretch")
            st.json(frame["trace"]["changes"])
        with health:
            st.json(cycle["health"])
            st.caption("Fonte solar simulation_weather: condição sintética declarada, sem internet.")
        st.caption("Arquivos desta execução: "+st.session_state.sim_folder)
    panel()
