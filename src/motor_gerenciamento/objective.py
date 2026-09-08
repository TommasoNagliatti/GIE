import numpy as np
def build_objective(layout,inputs,c):
    cost=np.zeros(layout.size)
    for t in range(c.horizon):
        values={'grid_import_kw':c.weight_grid_import+c.weight_grid_throughput,
                'grid_export_kw':c.weight_solar_export+c.weight_grid_throughput,
                'battery_charge_kw':c.weight_cycle,'battery_discharge_kw':c.weight_cycle,
                'grid_over_target_kw':c.weight_grid_over,
                'ev_unserved_kw':c.weight_ev_unserved*(1+inputs.queue_probability[t]),
                'ev_q90_headroom_shortfall_kw':c.weight_q90_shortfall*(1+inputs.queue_probability[t]),
                'reserve_deficit_kwh':c.weight_reserve}
        for name,value in values.items():cost[layout.at(name,t)]=c.step_h*value
    cost[layout.at('reserve_deficit_kwh',c.horizon-1)]+=c.weight_terminal_reserve
    return cost
