"""Visual explanation from existing structured evidence, never control logic."""
from html import escape
from demo.visuals import energy_svg
def diagram(cycle):
    svg=energy_svg(cycle).replace('viewBox="0 0 1080 415"','viewBox="0 0 1080 555"').replace('height="415" rx=','height="555" rx=')
    lb=cycle.get("load_balancer") or {}
    extra=''
    for i in range(1,5):
        x=25+(i-1)*265;device=lb.get(f"EVSE{i}",{});fault=device.get("state")=="fault";color="#ff8792" if fault else "#bc9aff";v=lb.get(f"evse_{i}_kw")
        if v is not None and v>0:extra+=f'<path d="M950 375 L950 420 L{x+110} 420 L{x+110} 450" fill="none" stroke="{color}" stroke-dasharray="5 4" marker-end="url(#a6da9ff)"/>'
        value="sem comando" if v is None else f"limite {v:.2f} kW"
        extra+=f'<rect x="{x}" y="450" width="240" height="70" rx="10" fill="#13283e" stroke="{color}"/><text x="{x+14}" y="474" fill="{color}" font-family="sans-serif" font-size="16">EVSE {i} {"· FALHA" if fault else ""}</text><text x="{x+14}" y="502" fill="#edf5fc" font-size="16">{value}</text>'
    return svg.replace('</svg>',extra+'</svg>')
def timeline(frames):
    rows=[]
    labels={"battery_charge_kw":"Carga bateria","battery_discharge_kw":"Descarga bateria","ev_block_limit_kw":"Limite EV","grid_export_plan_kw":"Exportação","grid_import_plan_kw":"Importação"}
    for f in frames:
        tr=f["trace"]
        for d in tr["changes"]:
            rows.append({"horário":tr["timestamp"],"registro":labels.get(d["action"],d["action"]),"valor":str(d["new_value"]),"motivos":", ".join(d["reason_codes"])})
        for e in tr["events"]:
            rows.append({"horário":e["timestamp"],"registro":e["code"],"valor":str(e.get("new_value")),"motivos":", ".join(e["reason_codes"])})
    return rows[-40:]
