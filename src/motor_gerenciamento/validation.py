import numpy as np
from .flow_allocator import allocate
class MaterialSimultaneityError(RuntimeError):pass
class PhysicalInfeasibleError(RuntimeError):pass
def validate_plan(plan,state,c):
    if len(plan)!=c.horizon:raise ValueError('Incomplete 48-step plan.')
    energy=state.battery_soc_pct*c.battery_capacity_kwh/100;max_balance=0.;max_soc=0.
    for row in plan:
        if not all(np.isfinite(v) for v in row.values() if isinstance(v,(int,float))):raise ValueError('Nonfinite plan.')
        g,x,ch,d=[row[k] for k in ['grid_import_plan_kw','grid_export_plan_kw','battery_charge_kw','battery_discharge_kw']]
        if min(ch,d)>c.simultaneity_kw or min(g,x)>c.simultaneity_kw:raise MaterialSimultaneityError('Material simultaneous charge/discharge or import/export. Stop; no MILP substitution.')
        for value,limit in [(g,c.grid_import_max_kw),(x,c.grid_export_max_kw),(ch,c.battery_charge_max_kw),(d,c.battery_discharge_max_kw),(row['ev_block_limit_kw'],c.ev_max_kw)]:
            if value < -c.tolerance or value>limit+c.tolerance:raise ValueError('Physical power limit violated.')
        if not -c.tolerance<=row['ev_served_kw']<=min(row['ev_expected_kw'],row['ev_block_limit_kw'])+c.tolerance:raise ValueError('EV service invalid.')
        if abs(row['solar_utilizado_kw']-row['solar_disponivel_kw'])>c.tolerance:raise ValueError('Solar curtailment detected.')
        surplus=max(0,row['solar_disponivel_kw']-row['building_kw']-row['ev_expected_kw'])
        if ch>surplus+c.tolerance:raise ValueError('Battery charging exceeds expected solar surplus.')
        balance=row['solar_utilizado_kw']+g+d-row['building_kw']-row['ev_served_kw']-ch-x
        max_balance=max(max_balance,abs(balance))
        if abs(balance)>c.tolerance:raise ValueError('Power balance violated.')
        energy+=c.step_h*(ch*c.charge_efficiency-d/c.discharge_efficiency)
        residual=abs(energy-row['battery_energy_kwh']);max_soc=max(max_soc,residual)
        if residual>c.tolerance or not c.energy_min-c.tolerance<=energy<=c.energy_max+c.tolerance:raise ValueError('Battery SOC dynamics violated.')
        if g-x+row['ev_block_limit_kw']-row['ev_served_kw']>c.grid_import_max_kw+c.tolerance:raise ValueError('EV advertised headroom not physically deliverable.')
        allocate(row,c.tolerance)
    return {'max_power_balance_error_kw':max_balance,'max_battery_dynamics_error_kwh':max_soc,'steps':len(plan),'valid':True}
