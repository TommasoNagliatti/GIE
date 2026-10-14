"""HTTP-only comparison view. Results are actual paired Energy V3 trajectories."""
import streamlit as st
import pandas as pd
from gie_panel.client import APIError

def render(client):
    st.header('Residência · sem bateria × com bateria')
    st.caption('Mesma casa, sol, veículos e rede. Bateria hipotética; cadastro oficial permanece sem bateria.')
    try:data=client.call('/panel/DEMO_CASA_001/comparison')
    except APIError as exc:st.error(str(exc));return
    if data.get('status')!='complete':
        st.info('O experimento precisa terminar antes de mostrar resultados. Nenhuma curva foi estimada para preencher o painel.')
        st.progress(min(1.,data.get('completed',0)/max(1,data.get('total',5760))))
        if data.get('error'):st.error(data['error'])
        st.code('python -B -m gie_panel.comparison',language='powershell')
        st.caption('Execute com o Python do motor e PYTHONPATH=src;src/gie_multistation/.deps. O comando gera checkpoints separados e não muda a residência.')
        st.button('Consultar comparação');return
    result=data['result']
    choice=st.selectbox('Período da comparação',list(result['periods']))
    p=result['periods'][choice];a=p['summary']['A'];b=p['summary']['B']
    st.caption(p['start']+' até '+p['end']+' · horários locais (UTC−03:00) · intervalos de 15 min')
    st.info('Os dias e a semana são recortes de uma simulação contínua de novembro. A bateria carrega o SOC dos dias anteriores; confira energia inicial e final. Novembro é um exemplo mensal, não uma projeção anual.')
    with st.expander('Hipóteses técnicas e compatibilidade GoodWe'):
        st.write('B: 5,40 kWh nominais, SOC 20–95% (4,05 kWh de janela), carga e descarga até 2,20 kW AC. O mês começa em 20%, sem energia inicial utilizável. Eficiência assumida: 95% em cada sentido (90,25% ida e volta).')
        st.write('Referência: LX U5.4-20, 47,5–57,6 V e 50 A. Limite AC de 2,2 kW conservador: 2,2/0,95 < 47,5×50/1000. Inversor já cadastrado: GW6000-ES-20, família ES G2, 6 kW, 120 A. Não é a variante M de 60 A.')
        st.write('A lista GoodWe permite LX U5.4-20 com ES G2, condicionada ao firmware ARM ≥02. Isso não certifica esta instalação: confirmar SKU regional, firmware, BMS, cabos, proteções e projeto elétrico.')
        st.markdown('[Compatibilidade oficial GoodWe](https://us.goodwe.com/Ftp/EN/Downloads/User%20Manual/GW_Battery%20Compatibility%20Overview-EN.pdf) · [Bateria LX U5.4-20](https://en.goodwe.com/Ftp/Downloads/Datasheet/AU/GW_Lynx%20Home%20U%20Series%20%28LV%29_5.4-20_Datasheet-AU.pdf) · [ES G2](https://es.goodwe.com/Ftp/Downloads/Datasheet/EMEA/GW_ES%20G2_Datasheet_EMEA-EN.pdf)')
        st.caption('Energy V3 inalterado: limite compartilhado conservador solar utilizado + carga + descarga ≤6 kW. A rede de 17 kW é da instalação simulada, não potência de passagem prometida pelo inversor. Cargas não são modeladas todas na saída backup.')
        st.json(result['configurations']['B'])
    delta=a['import_kwh']-b['import_kwh']
    with st.container(horizontal=True):
        for label,value in zip(['Rede sem bateria','Rede com bateria','Redução de importação','Perdas de armazenamento'],[a['import_kwh'],b['import_kwh'],delta,b['loss_kwh']]):st.metric(label,f'{value:.2f} kWh',width=200)
    st.subheader('Mesmas condições · resultados lado a lado')
    fields=[('Solar disponível / casa / EV solicitado',['solar_kw','building_kw','ev_demand_kw'],'Potência (kW)'),('Trocas com a rede',['grid_import_kw','grid_export_kw'],'Potência (kW)'),('Carga e descarga',['charge_kw','discharge_kw'],'Potência (kW)'),('Energia armazenada',['stored_kwh'],'Energia (kWh)'),('SOC',['soc_pct'],'SOC (%)'),('Atendimento dos veículos',['ev_demand_kw','ev_served_kw'],'Potência (kW)')]
    names={'solar_kw':'Solar','building_kw':'Casa','ev_demand_kw':'EV solicitado','grid_import_kw':'Importação','grid_export_kw':'Exportação','charge_kw':'Carga','discharge_kw':'Descarga','stored_kwh':'Armazenada','soc_pct':'SOC','ev_served_kw':'EV atendido'}
    colors={'solar_kw':'#ffd166','building_kw':'#5de2bd','ev_demand_kw':'#ffad73','grid_import_kw':'#69baff','grid_export_kw':'#45dccf','charge_kw':'#c4a0ff','discharge_kw':'#f392ce','stored_kwh':'#c4a0ff','soc_pct':'#c4a0ff','ev_served_kw':'#5de2bd'}
    # Same y-domain per paired chart: avoid exaggerating differences through auto-scales.
    import altair as alt
    for label,keys,unit in fields:
        st.markdown('**'+label+'**')
        maximum=max((r[k] for rows in p['rows'].values() for r in rows for k in keys if r[k] is not None),default=1)
        with st.container(horizontal=True):
            for v,title in zip(['A','B'],['A · sem bateria','B · bateria 5,4 kWh']):
                with st.container(width=450):
                    st.caption(title)
                    if v=='A' and keys==['soc_pct']:st.info('Não há bateria nem SOC neste cenário.');continue
                    frame=pd.DataFrame(p['rows'][v]);frame['timestamp']=pd.to_datetime(frame.timestamp).dt.tz_localize(None)
                    frame=frame[['timestamp']+keys].rename(columns=names).melt('timestamp',var_name='Série',value_name='Valor')
                    chart=alt.Chart(frame).mark_line().encode(x=alt.X('timestamp:T',title='Horário local',axis=alt.Axis(format='%d/%m %Hh',tickCount=4,labelAngle=-25)),y=alt.Y('Valor:Q',title=unit,scale=alt.Scale(domain=[0,max(1,maximum)*1.05]),axis=alt.Axis(format='.2f')),color=alt.Color('Série:N',scale=alt.Scale(domain=[names[k] for k in keys],range=[colors[k] for k in keys])),tooltip=[alt.Tooltip('timestamp:T',title='Instante',format='%d/%m/%Y %H:%M'), 'Série:N',alt.Tooltip('Valor:Q',format='.2f')]).properties(height=230).configure_axis(labelFontSize=12,titleFontSize=13).configure_legend(labelFontSize=12)
                    st.altair_chart(chart,width='stretch')
    st.subheader('Balanço do período')
    labels={'solar_kwh':'Solar disponível (kWh)','building_kwh':'Casa (kWh)','ev_requested_kwh':'EV solicitado (kWh)','ev_served_kwh':'EV atendido (kWh)','ev_unserved_kwh':'EV não atendido (kWh)','import_kwh':'Rede importada (kWh)','export_kwh':'Rede exportada (kWh)','solar_direct_kwh':'Solar direto nas cargas (kWh)','solar_to_storage_kwh':'Solar enviado ao armazenamento AC (kWh)','curtailed_kwh':'Solar limitado (kWh)','discharge_kwh':'Bateria entregue às cargas AC (kWh)','loss_kwh':'Perdas de armazenamento (kWh)','initial_kwh':'Energia inicial na bateria (kWh)','final_kwh':'Energia final na bateria (kWh)','delta_stored_kwh':'Variação da energia armazenada (kWh)','equivalent_cycles':'Ciclos equivalentes nominais','peak_grid_kw':'Pico de importação (kW)','limited_intervals':'Intervalos EV limitados (15 min)'}
    st.dataframe(pd.DataFrame([{'Indicador':label,'A · sem bateria':a[k],'B · com bateria':b[k]} for k,label in labels.items()]).style.format({'A · sem bateria':'{:.2f}','B · com bateria':'{:.2f}'}),hide_index=True,width='stretch')
    st.subheader('O que isso significa para a casa?')
    st.write(f'A bateria alterou a compra de energia em {delta:.2f} kWh neste período. O solar direto foi {b["solar_direct_kwh"]:.2f} kWh e {b["charge_kwh"]:.2f} kWh foram enviados para armazenamento. A exportação passou de {a["export_kwh"]:.2f} para {b["export_kwh"]:.2f} kWh.')
    st.write(f'No armazenamento perderam-se {b["loss_kwh"]:.2f} kWh. A bateria terminou com {b["delta_stored_kwh"]:.2f} kWh a mais que no início e realizou {b["equivalent_cycles"]:.2f} ciclos equivalentes (energia DC descarregada / 5,4 kWh). Não confundir com ciclos de garantia.')
    st.write(f'O pico da rede passou de {a["peak_grid_kw"]:.2f} para {b["peak_grid_kw"]:.2f} kW. Houve {a["limited_intervals"]} intervalos de recarga limitada em A e {b["limited_intervals"]} em B.')
    st.caption('Cortes EV são contados acima de 0,1 W, separando a tolerância numérica do solver de uma limitação de carga. Dados brutos e energia residual permanecem no CSV; nenhuma precisão do motor foi alterada.')
    st.caption('Solar direto é a parcela solar utilizada menos exportação e carga da bateria; não inclui novamente a descarga. O balanço inclui perdas, solar limitado e mudança de SOC. Despacho condicionado às previsões existentes, não conhecimento perfeito do futuro.')
    st.warning('Benefício energético não é retorno financeiro. Não há tarifa de compra/exportação configurada neste experimento nem custo de bateria/instalação: não calculamos economia em reais ou payback.')
    with st.expander('Rastreabilidade e validação'):
        st.write('Execução: '+result['run_id']);st.json(dict(checkpoints=result['checkpoint_paths'],hashes=result['inputs_sha256'],balances={v:{k:x for k,x in p['summary'][v].items() if 'error' in k} for v in ('A','B')}))
    st.download_button('Baixar dados dos dois cenários (CSV)',pd.concat([pd.DataFrame(rows).assign(cenario=v) for v,rows in p['rows'].items()]).to_csv(index=False),file_name='comparacao_residencial.csv',mime='text/csv')

