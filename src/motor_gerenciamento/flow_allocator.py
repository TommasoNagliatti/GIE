"""Logical accounting: solar->building/EV/battery/grid; battery->building/EV."""
def allocate(row,tolerance=1e-5):
    loads={'building':float(row['building_kw']),'ev':float(row['ev_served_kw']),'battery':float(row['battery_charge_kw']),'grid':float(row['grid_export_plan_kw'])}
    supply={'solar':float(row['solar_utilizado_kw']),'battery':float(row['battery_discharge_kw']),'grid':float(row['grid_import_plan_kw'])}
    order={'solar':['building','ev','battery','grid'],'battery':['building','ev'],'grid':['building','ev']}
    flows={}
    for source,targets in order.items():
        for target in targets:
            value=min(max(0,supply[source]),max(0,loads[target]))
            flows[f'{source}_to_{target}_kw']=value;supply[source]-=value;loads[target]-=value
    if max([abs(v) for v in list(supply.values())+list(loads.values())])>tolerance:raise ValueError('Flow allocation does not close.')
    return flows
