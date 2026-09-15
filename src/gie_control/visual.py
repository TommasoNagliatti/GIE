"""Display representation only. None/unknown never means a safe zero command."""
EPS=1e-5

def visual_for(result):
    n=result['numeric_state'];valid=result['execution_allowed']
    positive=lambda key: n.get(key) is not None and n[key]>EPS
    v={'valid':valid,'commands_valid':valid,'solar_active':positive('solar_kw'),
       'building_active':positive('building_kw')}
    for name,key in [('grid_importing','grid_import_kw'),('grid_exporting','grid_export_kw'),
                     ('battery_charging','battery_charge_kw'),('battery_discharging','battery_discharge_kw')]:
        v[name]=positive(key) if valid else None
    v['battery_flow']=('charging' if v['battery_charging'] else 'discharging' if v['battery_discharging'] else 'idle') if valid else 'unknown'
    v['grid_flow']=('importing' if v['grid_importing'] else 'exporting' if v['grid_exporting'] else 'idle') if valid else 'unknown'
    v['solar']='active' if v['solar_active'] else 'inactive'
    v['evses']={}
    for i in range(1,5):
        d=n['evses'][f'EVSE{i}'];power=n['evse_setpoints_kw'][i-1]
        fault=d.get('state')=='fault';active=power is not None and power>EPS and not fault
        state='fault' if fault else 'offline' if d.get('state')=='offline' else 'disconnected' if not d.get('connected') else 'charging' if active else 'idle'
        v[f'evse_{i}_active']=active if valid else None
        v[f'evse_{i}_fault']=fault
        v['evses'][f'EVSE{i}']=state if valid or fault else 'unknown'
    return v
