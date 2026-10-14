"""Presentation only: no dispatch, inference or physical-flow fabrication."""
from html import escape
from math import isfinite
from datetime import datetime

COLORS=dict(solar='#ffd166',grid='#69baff',battery='#c4a0ff',load='#5de2bd')

def number(v):return isinstance(v,(int,float)) and isfinite(v)
def fmt(v,unit='kW'):return f'{v:.2f} {unit}' if number(v) else 'Não informado'

def topology(n,equipment,first):
    nodes=[dict(id='solar',name='Solar utilizado' if number(first.get('solar_used_kw')) else 'Solar informado',x=145,y=70,value=first.get('solar_used_kw',n.get('solar_kw')),color=COLORS['solar'],direction='in'),
           dict(id='import',name='Rede · entrada',x=145,y=180,value=n.get('grid_import_kw'),color=COLORS['grid'],direction='in'),
           dict(id='building',name='Edificação',x=755,y=70,value=n.get('building_kw'),color=COLORS['load'],direction='out'),
           dict(id='ev',name='Veículos',x=755,y=180,value=n.get('ev_served_kw'),color=COLORS['load'],direction='out'),
           dict(id='export',name='Rede · saída',x=755,y=290,value=n.get('grid_export_kw'),color=COLORS['grid'],direction='out')]
    batteries=equipment.get('batteries',[])
    for i,b in enumerate(batteries):
        d=first.get('batteries',{}).get(b['battery_id'],{})
        charge=d.get('charge_kw');discharge=d.get('discharge_kw')
        if b.get('aggregate'):charge=n.get('battery_charge_kw');discharge=n.get('battery_discharge_kw')
        active_charge=number(charge) and charge>1e-4
        row_count=min(3,len(batteries)-(i//3)*3)
        nodes.append(dict(id=b['battery_id'],name=b['battery_id'],x=450+(i%3-(row_count-1)/2)*290,y=430+140*(i//3),value=charge if active_charge else discharge,color=COLORS['battery'],direction='out' if active_charge else 'in',subtitle='Carregando' if active_charge else 'Descarregando' if number(discharge) and discharge>1e-4 else 'Em espera' if number(discharge) and number(charge) else 'Sem dados',charge=charge,discharge=discharge))
    return nodes

def svg(n,equipment,first):
    nodes=topology(n,equipment,first);height=505+140*((len(equipment['batteries'])-1)//3) if equipment.get('batteries') else 365
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {height}" font-family="Arial, sans-serif" role="img" aria-label="Fluxo energético instantâneo; somente setas com fluxo positivo">', '<rect width="900" height="100%" rx="18" fill="#111d2b"/>','<defs>']
    for color in COLORS.values():parts.append(f'<marker id="arrow{color[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>')
    parts.append('</defs>')
    for node in nodes:
        if not number(node['value']) or node['value']<=1e-4:continue
        x=node['x'];y=node['y'];vertical=y>=430
        start=(450,245) if vertical else (515 if x>450 else 385,180)
        end=(x,y-50) if vertical else (x-126 if x>450 else x+126,y)
        if node['direction']=='in':start,end=end,start
        color=node['color'];parts.append(f'<path data-flow="{escape(node["id"])}" d="M {start[0]} {start[1]} L {end[0]} {end[1]}" stroke="{color}" stroke-width="4" fill="none" marker-end="url(#arrow{color[1:]})"/>')
    parts.append('<rect x="385" y="135" width="130" height="110" rx="20" fill="#25364a" stroke="#b9c9dc"/><text x="450" y="177" fill="white" font-size="21" text-anchor="middle">Sistema</text><text x="450" y="207" fill="#e0e8f0" font-size="17" text-anchor="middle">barramento</text>')
    for node in nodes:
        x=node['x'];y=node['y'];color=node['color'];sub=node.get('subtitle','')
        parts.append(f'<rect x="{x-125}" y="{y-48}" width="250" height="96" rx="14" fill="#18283b" stroke="{color}" stroke-width="2"/><text x="{x}" y="{y-17}" text-anchor="middle" fill="{color}" font-size="21" font-weight="bold">{escape(node["name"])}</text><text x="{x}" y="{y+13}" text-anchor="middle" fill="white" font-size="23">{escape(fmt(node["value"]))}</text>')
        if sub:parts.append(f'<text x="{x}" y="{y+36}" text-anchor="middle" fill="#e3e9f2" font-size="16">{sub}</text>')
    return ''.join(parts)+'</svg>'

def accumulated(rows,mode):
    if mode not in ('REPLAY','NORMAL') or not rows:return None
    try:
        dates=[datetime.fromisoformat(r['timestamp']) for r in rows]
        if any((b-a).total_seconds()!=900 for a,b in zip(dates,dates[1:])):return None
        fields=['solar_kw','building_kw','ev_served_kw','grid_import_kw','grid_export_kw']
        if any(not number(r.get(k)) for r in rows for k in fields):return None
        return {k:sum(r[k] for r in rows)*.25 for k in fields}
    except (KeyError,TypeError,ValueError):return None

def render(n,equipment,first,history,mode,valid=True):
    import streamlit as st
    st.subheader('Agora · potência instantânea (kW)')
    if not valid:
        st.warning('Sem decisão válida: nenhum fluxo atual é desenhado.');return
    st.image(svg(n,equipment,first),width='stretch')
    st.caption('Amarelo: solar · azul: rede · roxo: baterias · verde: consumo. Setas mostram somente potências positivas, através do barramento comum; não representam cabos físicos.')
    st.caption('Resíduos até 0,1 W não geram setas ou aviso de corte. Em telas pequenas, use o botão de tela cheia para ampliar o diagrama.')
    st.markdown('**O que o MPC decidiu neste intervalo**')
    if number(n.get('grid_import_kw')) and n['grid_import_kw']>1e-4:st.write('A rede complementa o atendimento: '+fmt(n['grid_import_kw'])+'.')
    if number(n.get('grid_export_kw')) and n['grid_export_kw']>1e-4:st.write('Há energia excedente saindo para a rede: '+fmt(n['grid_export_kw'])+'.')
    for node in topology(n,equipment,first):
        if 'charge' in node:st.write(node['name']+': '+node['subtitle'].lower()+' · '+fmt(node['value'])+'.')
    if number(n.get('ev_unserved_kw')) and n['ev_unserved_kw']>1e-4:st.write('A recarga foi limitada em '+fmt(n['ev_unserved_kw'])+' neste intervalo; consulte as restrições abaixo.')
    else:st.write('Nenhum corte EV informado neste intervalo.' if not number(n.get('ev_unserved_kw')) else 'A demanda EV informada foi atendida integralmente.')
    if number(first.get('solar_curtailed_kw')) and first['solar_curtailed_kw']>1e-4:st.write('Solar limitado pelo despacho: '+fmt(first['solar_curtailed_kw'])+'.')
    st.caption('Descrição do despacho observado; não atribui uma causa que o solver não informou.')
    totals=accumulated(history,mode)
    st.subheader('Acumulado · energia (kWh)')
    if totals:
        st.caption(f'Janela exibida: {len(history)} intervalos consecutivos de 15 min ({len(history)*.25:.2f} h), incluindo o intervalo atual simulado. Não é medição real nem total vitalício.')
        with st.container(horizontal=True):
            for name,key in [('Solar disponível','solar_kw'),('Edificação','building_kw'),('EV atendido','ev_served_kw'),('Rede comprada','grid_import_kw'),('Rede exportada','grid_export_kw')]:st.metric(name,fmt(totals[key],'kWh'),width=180)
    else:st.info('Acumulado indisponível: cenas avulsas, lacunas ou dados insuficientes não são somados como energia real.')

