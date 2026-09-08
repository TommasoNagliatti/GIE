"""Fast deterministic realization guard, used by simulation / future telemetry layer."""
from .validation import PhysicalInfeasibleError
from .flow_allocator import allocate
from math import isfinite
def apply_first(decision,state,building_kw,ev_demand_kw,solar_kw,c):
    if not all(isfinite(v) and v>=0 for v in (building_kw,ev_demand_kw,solar_kw)) or solar_kw>c.pv_ac_max_kw:raise ValueError('Invalid plant measurement.')
    if not c.soc_min_pct<=state.battery_soc_pct<=c.soc_max_pct:raise ValueError('Invalid measured SOC.')
    energy=state.battery_soc_pct*c.battery_capacity_kwh/100
    charge_cap=min(c.battery_charge_max_kw,max(0,(c.energy_max-energy)/(c.step_h*c.charge_efficiency)))
    discharge_cap=min(c.battery_discharge_max_kw,max(0,(energy-c.energy_min)*c.discharge_efficiency/c.step_h))
    capacity=c.grid_import_max_kw+solar_kw+discharge_cap-building_kw
    if capacity < -c.tolerance:raise PhysicalInfeasibleError('Actual mandatory load cannot be served within physical limits.')
    # Lexicographic projection: maximize actual EV service, then minimize the
    # change in signed battery power z=discharge-charge. Q90 is not a bound.
    served=min(ev_demand_kw,c.ev_max_kw,max(0,capacity))
    # V1.1: actual surplus only. No grid-to-battery recourse is allowed.
    charge_cap=min(charge_cap,max(0,solar_kw-building_kw-ev_demand_kw))
    load=building_kw+served-solar_kw
    lower=max(-charge_cap,load-c.grid_import_max_kw)
    upper=min(discharge_cap,max(0,load),load+c.grid_export_max_kw)
    if lower>upper+c.tolerance:raise PhysicalInfeasibleError('No feasible execution projection.')
    # Store measured surplus before exporting when there is battery room.
    target=-charge_cap if load<0 else decision['battery_discharge_kw']-decision['battery_charge_kw']
    z=min(upper,max(lower,target))
    discharge=max(0,z);charge=max(0,-z)
    safe_limit=min(c.ev_max_kw,max(0,c.grid_import_max_kw+solar_kw+z-building_kw))
    limit=min(safe_limit,max(decision['ev_block_limit_kw'],served))
    net=load-z
    after=energy+c.step_h*(charge*c.charge_efficiency-discharge/c.discharge_efficiency)
    row=dict(timestamp=decision['timestamp'],building_kw=building_kw,ev_expected_kw=ev_demand_kw,ev_high_kw=decision['ev_high_kw'],
        solar_disponivel_kw=solar_kw,solar_utilizado_kw=solar_kw,ev_served_kw=served,ev_block_limit_kw=limit,
        ev_unserved_kw=ev_demand_kw-served,ev_q90_headroom_shortfall_kw=max(0,decision['ev_high_kw']-limit),
        grid_import_plan_kw=max(0,net),grid_export_plan_kw=max(0,-net),grid_over_target_kw=max(0,net-c.grid_target_kw),
        battery_charge_kw=charge,battery_discharge_kw=discharge,battery_energy_kwh=after,
        battery_soc_before_pct=state.battery_soc_pct,battery_soc_after_pct=after/c.battery_capacity_kwh*100,
        reserve_deficit_kwh=max(0,c.energy_reserve-after))
    row['planned_ev_block_limit_kw']=decision['ev_block_limit_kw']
    row['planned_ev_expected_kw']=decision['ev_expected_kw']
    row['ev_demand_above_forecast']=ev_demand_kw>decision['ev_expected_kw']+c.tolerance
    row['ev_block_limit_relaxed']=limit>decision['ev_block_limit_kw']+c.tolerance
    row['execution_adjusted']=any(abs(row[k]-decision[k])>c.tolerance for k in ['battery_charge_kw','battery_discharge_kw','ev_block_limit_kw'])
    # Upward relaxation is normal operation, not a safety failure.
    row['safety_override']=limit<decision['ev_block_limit_kw']-c.tolerance
    row['flows']=allocate(row,c.tolerance)
    if row['flows'].get('grid_to_battery_kw',0)>c.tolerance:raise ValueError('Grid charging forbidden.')
    if not c.energy_min-c.tolerance<=after<=c.energy_max+c.tolerance:raise ValueError('Execution SOC invalid.')
    return row
