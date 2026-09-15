"""Optional UI. All control and result transformations live in gie_control."""
import pandas as pd
import streamlit as st
from gie_control import GIEControl
from gie_control.profile import load_profile
from gie_control.scenarios import EVENTS
from demo.simulation.view import diagram
from demo.high_autonomy_v2.control_bridge import run_demo

def render(mode):
    if 'gie_control' not in st.session_state:st.session_state.gie_control=GIEControl(demo_runner=run_demo)
    control=st.session_state.gie_control
    desired='PRESENTATION' if mode=='Presentation' else 'MANUAL_DEMO'
    if control.get_mode()!=desired:control.set_mode(desired)
    profile,_=load_profile()
    st.title('High Autonomy V2 · '+mode)
    st.caption(f"{profile['solar_dc_kwp']} kWp solar / {profile['solar_ac_kw']} kW AC · bateria {profile['battery_capacity_kwh']:,} kWh · sem reserva operacional")
    st.info('Cenas independentes e offline. Entradas e previsões demonstrativas explícitas; decisões calculadas pelo MPC V2 real. Setpoints são limites, não medições de consumo.')
    if desired=='PRESENTATION':
        sec=st.selectbox('Intervalo entre cenas (segundos)',[5,10,15],index=1,key='presentation_interval')
        if sec!=control.interval:control.set_presentation_interval(sec)
        loop=st.checkbox('Repetir ao terminar',key='presentation_loop')
        control.set_loop(loop)
        @st.fragment(run_every=1.0)
        def player():
            cols=st.columns(5)
            if cols[0].button('Iniciar',key='p_start'):
                if control.playing:pass
                elif control.result is None:control.start_presentation()
                else:control.resume_presentation()
            if cols[1].button('Pausar',key='p_pause'):control.pause_presentation()
            if cols[2].button('Cena anterior',key='p_prev'):control.previous_scene()
            if cols[3].button('Próxima cena',key='p_next'):control.next_scene()
            if cols[4].button('Reiniciar',key='p_reset'):control.stop_presentation()
            control.tick();p=control.get_presentation_state()
            st.subheader(f"Cena {p['scene_number']:02d} / 16 — {p['name']}")
            st.caption('Em reprodução' if p['playing'] else 'Pausado')
            show_result(control)
        player()
    else:
        st.caption('Os botões mudam apenas a telemetria demonstrativa. O MPC decide os fluxos; o SOC é uma entrada da cena, não uma trajetória contínua.')
        cols=st.columns(3)
        for i,(code,label) in enumerate(EVENTS.items()):
            if cols[i%3].button(label,key='manual_'+code):
                with st.spinner('GIE calculando a decisão…'):control.trigger_demo_event(code)
        if st.button('Reset',key='manual_reset'):
            with st.spinner('Restaurando entrada demonstrativa…'):control.reset_demo()
        if control.get_state() is None:
            st.caption('Escolha um evento ou Reset para calcular a primeira decisão.')
        else:show_result(control)

def show_result(control):
    result=control.get_state()
    if result is None:return
    n=result['numeric_state'];msg=result['primary_message']
    with st.container(border=True):
        st.caption('DECISÃO ATUAL · '+result['timestamp'])
        st.subheader(msg['title']);st.write(msg['text'])
    if not result['execution_allowed']:
        st.error('Entrada demonstrativa sem decisão segura. Nenhum novo comando foi autorizado. Use Reset ou ajuste as entradas.')
        st.json(result['health']);st.json(result['visual_state']);return
    metrics=[('Prédio',n['building_kw'],'kW'),('Solar',n['solar_kw'],'kW'),('EV realizado',n['ev_served_kw'],'kW'),
             ('SOC antes',n['battery_soc_pct'],'%'),('SOC após',n['battery_soc_after_pct'],'%')]
    for col,(label,value,unit) in zip(st.columns(5),metrics):col.metric(label,f'{value:.2f} {unit}' if value is not None else 'indisponível')
    st.image(diagram(result),width='stretch')
    tabs=st.tabs(['Energy View','Events / Decisions','Maquete / JSON'])
    with tabs[0]:
        st.dataframe(pd.DataFrame([{'Grandeza':k,'Valor':v} for k,v in n.items() if isinstance(v,(float,int))]),hide_index=True,width='stretch')
        st.dataframe(pd.DataFrame(n['evses']).T,width='stretch')
    with tabs[1]:
        st.dataframe(pd.DataFrame([{'Horário':r['timestamp'],'Modo':r['mode'],'Decisão':r['message']['title']} for r in control.message_history[-20:]]),hide_index=True,width='stretch')
        for message in result['messages'][1:]:st.write(message['title']+' — '+message['text'])
        st.json(result['events']);st.json(result['health'])
    with tabs[2]:
        st.caption('Estado visual somente; nenhum comando de hardware enviado.')
        st.json(result['visual_state']);st.json(n)
