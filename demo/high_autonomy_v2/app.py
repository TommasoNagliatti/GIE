import sys,json,time
from pathlib import Path
import pandas as pd
import streamlit as st
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from demo.simulation.view import diagram,timeline
st.set_page_config(page_title="GIE · High Autonomy V2",page_icon="⚡",layout="wide")
st.markdown("<style>.stApp{background:#081425}div[data-testid=stMetric]{background:#13283e;padding:12px;border-radius:10px}div[data-testid=stMetricValue]{font-size:22px}</style>",unsafe_allow_html=True)
@st.cache_data
def load():
 return {"Grid Connected V1":json.loads((ROOT/"outputs/simulation/v1/run_24h/simulation.json").read_text(encoding="utf-8"))["cycles"],"High Autonomy V2":json.loads((ROOT/"outputs/high_autonomy_v2/comparison/v2_cycles.json").read_text(encoding="utf-8"))}
data=load()
if "step" not in st.session_state:st.session_state.step=1;st.session_state.play=False;st.session_state.next_due=0.
st.sidebar.title("⚡ GIE · Simulation Mode")
profile=st.sidebar.radio("Perfil energético",list(data),index=1)
v2=profile=="High Autonomy V2"
from gie_control.profile import load_profile
official_profile,_=load_profile(ROOT)
area=st.sidebar.radio("Área",["V1 × V2 Comparison","Presentation","Manual Demo"])
if area!="V1 × V2 Comparison" and v2:
 from demo.high_autonomy_v2.presentation_view import render
 render(area)
 st.stop()
elif area!="V1 × V2 Comparison":
 st.sidebar.info("Presentation e Manual Demo usam High Autonomy V2. Selecione esse perfil para acessá-los.")
st.sidebar.info("Reprodução da comparação de 24h. Decisões calculadas pelo MPC; nenhuma simulação é recalculada ao trocar o perfil.")
st.sidebar.metric("Solar instalado",f"{official_profile['solar_dc_kwp']} kWp / {official_profile['solar_ac_kw']} kW AC" if v2 else "150 kWp / 125 kW AC")
st.sidebar.metric("Bateria instalada",f"{official_profile['battery_capacity_kwh']:,} kWh" if v2 else "200 kWh")
st.sidebar.caption(f"Potência bateria: ±{official_profile['battery_charge_max_kw']} kW" if v2 else "Potência bateria: ±100 kW")
st.sidebar.caption("V2: SOC físico 20–95%, sem reserva operacional. Rede máxima 350 kW; EV 88 kW.")
speed=st.sidebar.selectbox("Segundos por ciclo",[60.,15.,7.5],index=1)
@st.fragment(run_every="1s" if st.session_state.play else None)
def panel():
 st.title(profile);st.caption("Mesmo prédio, EVs e eventos · revisão isolada · V1 preservada")
 a,b,c,d=st.columns(4)
 if a.button("Iniciar"):st.session_state.play=True;st.session_state.next_due=time.monotonic()+speed;st.rerun()
 if b.button("Pausar"):st.session_state.play=False;st.rerun()
 if c.button("Próximo passo"):st.session_state.step=min(96,st.session_state.step+1)
 if d.button("Reiniciar"):st.session_state.step=1;st.session_state.play=False;st.rerun()
 if st.session_state.play and time.monotonic()>=st.session_state.next_due:
  st.session_state.step=min(96,st.session_state.step+1);st.session_state.next_due=time.monotonic()+speed
  if st.session_state.step==96:st.session_state.play=False;st.rerun()
 st.number_input("Ciclo (1–96)",1,96,key="step")
 i=st.session_state.step-1;frames=data[profile][:i+1];cycle=frames[-1]["cycle"];m=cycle["management"]
 imported=sum(x["cycle"]["management"]["grid_import_plan_kw"]*.25 for x in frames)
 consumed=sum((x["cycle"]["current_state"]["building_kw"]+x["cycle"]["management"]["first_decision"]["ev_served_kw"])*.25 for x in frames)
 st.subheader(cycle["decision_time"])
 for col,label,val in zip(st.columns(4),["SOC após","Carga / descarga","Rede acumulada","Autossuficiência"],[f'{m["battery_soc_after_pct"]:.2f}%',f'{m["battery_charge_kw"]:.1f} / {m["battery_discharge_kw"]:.1f} kW',f'{imported:.2f} kWh',f'{100*(1-imported/consumed):.2f}%']):col.metric(label,val)
 st.image(diagram(cycle),width="stretch")
 history,events,health=st.tabs(["Histórico","Decisões e eventos","Health"])
 with history:
  rows=[{"timestamp":x["cycle"]["decision_time"],"SOC":x["cycle"]["management"]["battery_soc_after_pct"],"Carga":x["cycle"]["management"]["battery_charge_kw"],"Descarga":x["cycle"]["management"]["battery_discharge_kw"],"Rede":x["cycle"]["management"]["grid_import_plan_kw"],"Solar":x["cycle"]["current_state"]["solar_kw"]} for x in frames]
  df=pd.DataFrame(rows).set_index("timestamp");st.line_chart(df[["Carga","Descarga","Rede","Solar"]]);st.line_chart(df[["SOC"]])
 with events:st.dataframe(timeline(frames[-4:]),width="stretch")
 with health:st.json(cycle["health"])
panel()
