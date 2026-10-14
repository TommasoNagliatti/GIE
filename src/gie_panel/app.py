"""Local panel: HTTP responses only; never imports an MPC or station runtime."""
import math,sys,time
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import streamlit as st
import pandas as pd
import altair as alt
from gie_panel.client import Client,APIError

NAMES={'Commercial_HighAutonomy_V2':'Prédio comercial','DEMO_POSTO_24H_001':'Posto 24 horas','DEMO_CASA_001':'Residência','NEW_NO_HISTORY':'Estação BASELINE'}
st.set_page_config(page_title='GIE · Estações',page_icon='⚡',layout='wide')
st.title('GIE · Painel multiestação')
st.warning('SIMULAÇÃO — NENHUM EQUIPAMENTO REAL CONTROLADO')
def api():return Client()
def fmt(value,unit=''):
    return '—' if value is None or not isinstance(value,(int,float)) or not math.isfinite(value) else f'{value:.2f} {unit}'.strip()
try:
    registered=api().call('/v1/stations')
except APIError as exc:
    st.error(str(exc));st.stop()
ids=[x['config']['station_id'] for x in registered if x['config']['station_id'] in NAMES]
sid=st.sidebar.selectbox('Estação',ids,format_func=lambda s:NAMES[s])
st.sidebar.caption(sid)
area=st.sidebar.radio('Ambiente',['Replay salvo','Simulação interativa'])
st.sidebar.info('Replay só lê evidências. A simulação cria checkpoints novos e isolados por estação.')
st.sidebar.link_button('Painel original · High Autonomy V2','http://127.0.0.1:8503')
path='/panel/'+sid
try:catalog=api().call(path+'/catalog')
except APIError as exc:st.error(str(exc));st.stop()
scenarios=catalog['scenarios']
scenario=st.sidebar.selectbox('Cenário',[s['id'] for s in scenarios],format_func=lambda i:next(s['name'] for s in scenarios if s['id']==i))
interval=st.sidebar.select_slider('Segundos por avanço',options=[1,2,5,10,15],value=5)
st.sidebar.caption('Resolução energética: 15 min. A velocidade altera apenas a reprodução visual.')
signature=(sid,area,scenario)
if st.session_state.get('signature')!=signature:
    st.session_state.update(signature=signature,playing=False,replay_index=0,next_due=0)

def graph(rows,columns):
    if not rows:return
    frame=pd.DataFrame(rows)
    selected=[c for c in columns if c in frame and frame[c].notna().any()]
    if not selected:return
    frame['timestamp']=pd.to_datetime(frame['timestamp'],utc=True)
    names={'building_kw':'Edificação','solar_kw':'Solar','grid_import_kw':'Importação','grid_export_kw':'Exportação','ev_demand_kw':'EV solicitado','ev_served_kw':'EV atendido','potencia_solicitada_prevista_kw':'EV previsto','solar_previsto_kw':'Solar previsto'}
    frame=frame.rename(columns=names)
    st.line_chart(frame,x='timestamp',y=[names.get(c,c) for c in selected],x_label='Instante (UTC)',y_label='Potência (kW)',height=240)

def render_view(response):
    st.caption(f"{sid} · {response.get('process')} · {response.get('mode','—')} · ciclo {response.get('cycle',0)} · geração {response.get('generation','—')}")
    model=response.get('model','—')
    if isinstance(model,dict):
        label=' · '.join(str(model[k]) for k in ['state','version','motor1','motor2'] if model.get(k)) or 'Modelos próprios da estação'
        st.caption('Modelo: '+label)
        with st.expander('Identidade dos modelos'):st.json(model)
    else:st.caption('Modelo: '+str(model))
    view=response.get('view')
    if not view:st.info('Inicialize a estação e execute um ciclo para obter dados.');return
    r=view['result'];n=r.get('numeric_state') or {};eq=view['equipment'];first=(r.get('management') or {}).get('first_decision') or {}
    st.caption(f"{view['source']} · último ciclo {r.get('timestamp','—')} · estado {r.get('status','—')}")
    if not r.get('execution_allowed'):st.error('Execução bloqueada. Não há decisão válida para aplicar.')
    for group in [[('Edificação','building_kw'),('Solar','solar_kw'),('Importação','grid_import_kw'),('Exportação','grid_export_kw')],[('EV solicitado','ev_demand_kw'),('EV atendido · simulado','ev_served_kw'),('EV não atendido','ev_unserved_kw')]]:
        for col,(name,k) in zip(st.columns(len(group)),group):col.metric(name,fmt(n.get(k),'kW'))
    tabs=st.tabs(['Fluxo e equipamentos','Previsão · 12h','Histórico','Mensagens e origem'])
    with tabs[0]:
        from gie_panel.flow import render
        render(n,eq,first,view.get('history') or [],response.get('mode'),r.get('execution_allowed',False))
        if sid in ('DEMO_CASA_001','DEMO_POSTO_24H_001'):
            st.caption('Prioridades do Energy V3: atender os veículos dentro dos limites técnicos; depois reduzir energia comprada da rede, aproveitar o solar e evitar circulação desnecessária. O horizonte é de 12 horas, mas somente os próximos 15 minutos são aplicados à simulação.')
        st.subheader('Baterias')
        if not eq['batteries']:st.info('Sem bateria instalada')
        for b in eq['batteries']:
            bid=b['battery_id'];d=first.get('batteries',{}).get(bid,{})
            soc=d.get('soc_after');energy=d.get('energy_after_kwh')
            if b.get('aggregate'):
                soc=n.get('battery_soc_after_pct');soc=soc/100 if soc is not None else None
                energy=soc*b['capacity_kwh'] if soc is not None else None
                d=dict(charge_kw=n.get('battery_charge_kw'),discharge_kw=n.get('battery_discharge_kw'))
            with st.container(border=True):
                st.markdown('**'+bid+(' · banco agregado original' if b.get('aggregate') else '')+'**')
                cols=st.columns(4)
                for col,label,val,unit in zip(cols,['SOC','Energia armazenada','Carga','Descarga'],[100*soc if soc is not None else None,energy,d.get('charge_kw'),d.get('discharge_kw')],['%','kWh','kW','kW']):col.metric(label,fmt(val,unit))
                st.caption(f"Cadastro disponível: {b.get('available','—')} · SOC {fmt(100*b['soc_min'])}–{fmt(100*b['soc_max'])}% · capacidade {fmt(b['capacity_kwh'],'kWh')} · limite carga/descarga {fmt(b['charge_kw'])}/{fmt(b['discharge_kw'])} kW")
        st.subheader('Carregadores')
        for e in eq['evses']:
            eid=e['evse_id'];d=(n.get('evses') or {}).get(eid,{})
            limits=first.get('evse_setpoints_kw') or {}
            authorized=limits.get(eid)
            if authorized is None and isinstance(n.get('evse_setpoints_kw'),list):
                pos=eq['evses'].index(e);vals=n['evse_setpoints_kw'];authorized=vals[pos] if pos<len(vals) else None
            with st.container(border=True):
                st.markdown('**'+eid+'**')
                st.write('Solicitado: '+fmt(d.get('requested_kw'),'kW')+' · limite autorizado: '+fmt(authorized,'kW'))
                st.caption(f"Conectado: {d.get('connected','não informado')} · disponível: {d.get('available','não informado')} · estado: {(r.get('visual_state') or {}).get('evses',{}).get(eid,'não informado')} · limite técnico {fmt(e['max_kw'],'kW')}")
        st.caption('Setpoints são limites matemáticos, não consumo medido. “—” significa dado indisponível.')
    with tabs[1]:
        forecasts=r.get('forecasts') or {};rows=forecasts.get('records') or []
        if sid=='DEMO_CASA_001':st.warning('Motor 2 residencial: baixa confiabilidade na previsão de eventos EV.')
        if rows:
            st.caption(f'{len(rows)} passos · 15 min por passo')
            graph(rows,['building_kw','potencia_solicitada_prevista_kw','solar_previsto_kw'])
            with st.expander('Dados e origem da previsão'):st.json(forecasts)
        else:st.info('Este artefato salvo não contém previsões. Não foram reconstruídas ou inventadas.')
    with tabs[2]:
        rows=view.get('history') or []
        graph(rows,['building_kw','solar_kw','grid_import_kw','grid_export_kw','ev_demand_kw','ev_served_kw'])
        if rows:
            frame=pd.DataFrame(rows);soccols=[c for c in frame if c.endswith('_soc_pct')]
            if soccols:st.line_chart(frame,x='timestamp',y=soccols,y_label='SOC (%)',height=200)
            st.dataframe(frame.round(2),hide_index=True)
    with tabs[3]:
        for msg in r.get('messages',[]):
            method=st.error if msg.get('severity') in ('critical','error') else st.warning if msg.get('severity')=='warning' else st.info
            method(msg.get('title','Aviso')+' — '+msg.get('text',''))
        st.json(r.get('provenance') or r.get('station_extension') or {})
        st.caption('physical_dispatch=false · hardware_commands_sent=false · commands_valid=false. Validade matemática não é autorização física.')

def alerts():
    st.subheader('Central de avisos · runtime interativo')
    st.caption('Independente do replay. Reconhecer confirma leitura; somente observações válidas podem resolver uma condição.')
    cols=st.columns(3)
    severity=cols[0].selectbox('Severidade',['Todas','info','warning','error','critical'])
    status=cols[1].selectbox('Status',['Todos','OPEN','ACKNOWLEDGED','RESOLVED'])
    equipment=cols[2].text_input('Equipamento (ID exato)')
    query={}
    if severity!='Todas':query['severity']=severity
    if status!='Todos':query['status']=status
    if equipment:query['equipment_id']=equipment
    items=api().call(path+'/alerts?'+urlencode(query))
    if not items:st.info('Nenhum aviso para este filtro.')
    for a in items:
        with st.expander(f"{a['severity'].upper()} · {a['title']} · {a['status']} · {a['equipment_id'] or sid}"):
            st.write(a['description']);st.caption(f"Ocorrências: {a['occurrence_count']} · primeira: {a['first_seen']} · última: {a['last_seen']}")
            st.json({k:a[k] for k in ['alert_id','reason_codes','numeric_context','provenance','acknowledged_at','resolved_at']})
            if a['status']=='OPEN' and st.button('Reconhecer',key=a['alert_id']):api().call(path+'/alerts/'+a['alert_id']+'/ack',{});st.rerun()
    with st.expander('Histórico persistente de eventos'):
        events=api().call(path+'/events')
        st.dataframe([dict(cursor=e['cursor'],evento=e['transition'],codigo=e['alert']['code'],status=e['alert']['status'],instante=e['alert']['detected_at']) for e in events],hide_index=True)
        st.caption('Primeiros 500 eventos; API oferece paginação por cursor para integração.')

@st.fragment(run_every=1)
def dashboard():
    try:
        cols=st.columns(4)
        if cols[0].button('▶ Reproduzir'):st.session_state.playing=True;st.session_state.next_due=time.monotonic()+interval
        if cols[1].button('Ⅱ Pausar'):st.session_state.playing=False
        advance=cols[2].button('Próximo · 15 min')
        reset=cols[3].button('Reiniciar replay' if area=='Replay salvo' else 'Novo teste isolado')
        due=st.session_state.playing and time.monotonic()>=st.session_state.next_due
        if area=='Replay salvo':
            count=next(s['cycles'] for s in scenarios if s['id']==scenario)
            if reset:st.session_state.replay_index=0;st.session_state.playing=False
            elif advance or due:st.session_state.replay_index=min(count-1,st.session_state.replay_index+1)
            response=api().call(path+'/replay?'+urlencode(dict(scenario=scenario,index=st.session_state.replay_index)))
            if st.session_state.replay_index>=count-1:st.session_state.playing=False
            st.progress((st.session_state.replay_index+1)/count)
        else:
            buttons=st.columns(4);initialize=buttons[0].button('Inicializar / retomar');buttons[1].button('Consultar estado')
            restart=buttons[2].button('Reiniciar worker');stop=buttons[3].button('Parar worker')
            fixture=st.selectbox('Entrada simulada',['normal','missing','stale','overload','offline']) if sid=='NEW_NO_HISTORY' else 'normal'
            if reset:response=api().call(path+'/reset',dict(scenario=scenario));st.session_state.playing=False
            elif initialize:response=api().call(path+'/initialize',{})
            elif stop:response=api().call(path+'/stop',{});st.session_state.playing=False
            elif restart:response=api().call(path+'/restart',{})
            elif advance or due:response=api().call(path+'/cycle',dict(fixture=fixture))
            else:response=api().call(path+'/state')
            if response.get('cycle',0)>=96 or (response.get('view') and not response['view']['result'].get('execution_allowed')):st.session_state.playing=False
            st.progress(min(response.get('cycle',0),96)/96)
            if response.get('scenario') and response['scenario']!=scenario:st.info('O teste ativo usa '+response['scenario']+'. Clique em Novo teste isolado para usar o cenário selecionado.')
            if sid=='Commercial_HighAutonomy_V2':
                with st.expander('Presentation · 16 cenas / Manual Demo'):
                    mode=st.selectbox('Modo',['NORMAL','PRESENTATION','MANUAL_DEMO'])
                    if st.button('Aplicar modo'):api().call(path+'/mode',dict(mode=mode));st.rerun()
                    if response.get('mode')=='PRESENTATION':
                        presentation=response.get('presentation') or {}
                        st.caption('Cena atual: '+str(presentation.get('scene_id','—'))+' · '+str(presentation.get('name',''))+' · '+('Reproduzindo' if presentation.get('playing') else 'Pausada'))
                        scene=st.selectbox('Cena',[f'{i:02d}' for i in range(1,17)])
                        if st.button('Ir para cena'):api().call(path+'/presentation',dict(action='scene',scene_id=scene));st.rerun()
                        for col,(label,action) in zip(st.columns(5),[('Iniciar','start'),('Pausar cenas','pause'),('Anterior','previous'),('Próxima','next'),('Reiniciar cenas','reset')]):
                            if col.button(label):api().call(path+'/presentation',dict(action=action));st.rerun()
                        loop=st.checkbox('Loop')
                        if st.button('Aplicar loop'):api().call(path+'/presentation',dict(action='loop',enabled=loop));st.rerun()
                        seconds=st.selectbox('Segundos por cena',[5,10,15])
                        if st.button('Aplicar intervalo'):api().call(path+'/presentation',dict(action='interval',seconds=seconds));st.rerun()
                    if response.get('mode')=='MANUAL_DEMO':
                        event=st.selectbox('Evento Manual Demo',['RESET','EV_PEAK','BUILDING_PEAK','SOLAR_DROP','SOLAR_STRONG','FAULT_EVSE1','FAULT_EVSE2','FAULT_EVSE3','FAULT_EVSE4','RECOVER_EVSES','SOC_HIGH','SOC_LOW'])
                        if st.button('Aplicar evento simulado'):api().call(path+'/manual',dict(event=event));st.rerun()
        if due or advance:st.session_state.next_due=time.monotonic()+interval
        render_view(response);alerts()
    except APIError as exc:
        st.session_state.playing=False;st.error(str(exc))
if sid=='DEMO_CASA_001':
    if st.sidebar.button('Comparar baterias',type='primary'):
        st.session_state.comparing=True;st.session_state.playing=False
    if st.session_state.get('comparing'):
        if st.sidebar.button('Voltar ao painel energético'):st.session_state.comparing=False;st.rerun()
        from gie_panel.comparison_ui import render as render_comparison
        render_comparison(api())
    else:dashboard()
else:dashboard()

