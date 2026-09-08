"""Small deterministic fallback; declares impossible mandatory-load scenarios."""
from .validation import PhysicalInfeasibleError
def greedy_plan(inputs,state,c):
    energy=state.battery_soc_pct*c.battery_capacity_kwh/100;rows=[]
    for t in range(c.horizon):
        b=float(inputs.building_kw[t]);pv=float(inputs.solar_kw[t]);expected=float(inputs.ev_expected_kw[t]);before=energy
        discharge_cap=min(c.battery_discharge_max_kw,max(0,(energy-c.energy_min)*c.discharge_efficiency/c.step_h))
        charge_cap=min(c.battery_charge_max_kw,max(0,(c.energy_max-energy)/(c.step_h*c.charge_efficiency)))
        net=b+expected-pv
        discharge=min(discharge_cap,max(0,net-c.grid_target_kw));charge=min(charge_cap,max(0,-net))
        served=min(expected,max(0,c.grid_target_kw+pv+discharge-b))
        grid=max(0,b+served+charge-pv-discharge);export=max(0,pv+discharge-b-served-charge)
        if grid>c.grid_import_max_kw+c.tolerance or export>c.grid_export_max_kw+c.tolerance:raise PhysicalInfeasibleError(f'Mandatory building demand infeasible at {inputs.timestamps[t]}; no safe schedule.')
        energy+=c.step_h*(charge*c.charge_efficiency-discharge/c.discharge_efficiency)
        limit=min(float(inputs.ev_high_kw[t]),max(served,served+c.grid_target_kw+max(0,grid-c.grid_target_kw)-(grid-export)))
        rows.append(dict(timestamp=str(inputs.timestamps[t]),building_kw=b,solar_disponivel_kw=pv,solar_utilizado_kw=pv,
            ev_expected_kw=expected,ev_high_kw=float(inputs.ev_high_kw[t]),ev_served_kw=served,ev_block_limit_kw=limit,
            ev_unserved_kw=expected-served,ev_q90_headroom_shortfall_kw=max(0,float(inputs.ev_high_kw[t])-limit),
            grid_import_plan_kw=grid,grid_export_plan_kw=export,grid_over_target_kw=max(0,grid-c.grid_target_kw),
            battery_charge_kw=charge,battery_discharge_kw=discharge,battery_energy_kwh=energy,
            battery_soc_before_pct=before/c.battery_capacity_kwh*100,battery_soc_after_pct=energy/c.battery_capacity_kwh*100,
            reserve_deficit_kwh=max(0,c.energy_reserve-energy)))
    return rows

