"""Read-only SVG view of current energy flows."""
from html import escape

def energy_svg(cycle):
    cur=cycle.get('current_state') or {};mg=cycle.get('management') or {};flows=cycle.get('flows') or {}
    def val(v):return '—' if v is None else f'{v:.2f}'
    def node(x,y,w,title,detail,color):
        return f'<rect x="{x}" y="{y}" width="{w}" height="72" rx="14" fill="#13283e" stroke="{color}"/><text x="{x+16}" y="{y+27}" fill="{color}" font-size="14" font-weight="700">{escape(title)}</text><text x="{x+16}" y="{y+53}" fill="#edf5fc" font-size="16">{escape(detail)}</text>'
    paths=[('solar_to_building_kw','M 550 75 C 680 65 760 90 835 148',690,73,'#f6c85f'),
        ('solar_to_ev_kw','M 560 100 C 740 150 740 290 835 305',680,190,'#f6c85f'),
        ('solar_to_battery_kw','M 435 85 C 320 60 255 120 210 157',275,100,'#f6c85f'),
        ('solar_to_grid_kw','M 435 105 C 270 170 320 260 210 322',305,255,'#f6c85f'),
        ('battery_to_building_kw','M 215 172 C 430 130 600 130 835 172',460,145,'#39d7b0'),
        ('battery_to_ev_kw','M 215 193 C 450 220 620 300 835 318',470,255,'#39d7b0'),
        ('grid_to_building_kw','M 215 327 C 410 300 620 185 835 183',490,205,'#6da9ff'),
        ('grid_to_ev_kw','M 215 342 L 835 342',490,360,'#6da9ff')]
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 415" role="img" aria-label="Fluxos de energia em kW"><defs>'
    for color in ['#f6c85f','#39d7b0','#6da9ff']:
        svg+=f'<marker id="a{color[1:]}" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="{color}"/></marker>'
    svg+='</defs><rect width="1080" height="415" rx="16" fill="#0b1b2d"/>'
    for key,path,x,y,color in paths:
        v=flows.get(key,0) or 0
        if v>1e-6:
            width=min(6,1.5+v/60)
            svg+=f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width}" opacity=".85" marker-end="url(#a{color[1:]})"/>'
            svg+=f'<rect x="{x-7}" y="{y-15}" width="97" height="23" rx="5" fill="#0b1b2d"/><text x="{x}" y="{y}" fill="{color}" font-size="13">{v:.2f} kW</text>'
    svg+=node(420,20,170,'SOLAR',val(cur.get('solar_kw'))+' kW','#f6c85f')
    svg+=node(25,140,190,'BATERIA','SOC '+val(cur.get('battery_soc_pct'))+'%','#39d7b0')
    svg+=node(25,300,190,'REDE','↓ '+val(mg.get('grid_import_plan_kw'))+'  ↑ '+val(mg.get('grid_export_plan_kw')),'#6da9ff')
    svg+=node(845,140,210,'PRÉDIO',val(cur.get('building_kw'))+' kW','#f0f4fa')
    svg+=node(845,300,210,'BLOCO EV','Limite '+val(mg.get('ev_block_limit_kw'))+' kW','#bc9aff')
    if not mg.get('execution_allowed'):
        svg+='<text x="540" y="230" text-anchor="middle" fill="#ff8792" font-size="23">EXECUÇÃO BLOQUEADA — sem novos comandos</text>'
    svg+='<text x="535" y="403" text-anchor="middle" fill="#829ab2" font-size="12">Setas: fluxos do ciclo · kW · Setpoints EV são limites, não consumo medido</text></svg>'
    return svg
