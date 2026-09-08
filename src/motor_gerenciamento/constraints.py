"""Continuous LP; counterfactual Q90 capacity supplied by grid recourse only."""
import numpy as np
from scipy.sparse import lil_matrix
NAMES=['grid_import_kw','grid_export_kw','battery_charge_kw','battery_discharge_kw','battery_energy_kwh',
       'ev_served_kw','ev_block_limit_kw','grid_over_target_kw','ev_unserved_kw','ev_q90_headroom_shortfall_kw','reserve_deficit_kwh']
class Layout:
    def __init__(self,n):self.n=n;self.size=n*len(NAMES)
    def at(self,name,t):return NAMES.index(name)*self.n+t
    def series(self,x,name):return np.asarray(x)[self.at(name,0):self.at(name,0)+self.n]
def build(inputs,state,c):
    n=c.horizon;layout=Layout(n);equal=[];rhs=[];upper=[];limits=[];bounds=[(0,None)]*layout.size
    def eq(terms,value):equal.append(terms);rhs.append(value)
    def ub(terms,value):upper.append(terms);limits.append(value)
    e0=state.battery_soc_pct*c.battery_capacity_kwh/100
    solar_load=np.minimum(inputs.solar_kw,inputs.building_kw+inputs.ev_expected_kw)
    ev_min=np.minimum(inputs.ev_expected_kw,np.maximum(0,inputs.solar_kw-inputs.building_kw))
    for t in range(n):
        j=lambda name:layout.at(name,t)
        for name,bound in [('grid_import_kw',(0,c.grid_import_max_kw)),('grid_export_kw',(0,c.grid_export_max_kw)),
            ('battery_charge_kw',(0,min(c.battery_charge_max_kw,float(max(0,inputs.solar_kw[t]-inputs.building_kw[t]-inputs.ev_expected_kw[t]))))),('battery_discharge_kw',(0,c.battery_discharge_max_kw)),
            ('battery_energy_kwh',(c.energy_min,c.energy_max)),('ev_served_kw',(float(ev_min[t]),float(inputs.ev_expected_kw[t]))),
            ('ev_block_limit_kw',(0,float(inputs.ev_high_kw[t])))]:bounds[j(name)]=bound
        eq({j('grid_import_kw'):1,j('grid_export_kw'):-1,j('battery_charge_kw'):-1,j('battery_discharge_kw'):1,j('ev_served_kw'):-1},float(inputs.building_kw[t]-inputs.solar_kw[t]))
        terms={j('battery_energy_kwh'):1,j('battery_charge_kw'):-c.step_h*c.charge_efficiency,j('battery_discharge_kw'):c.step_h/c.discharge_efficiency}
        if t:terms[layout.at('battery_energy_kwh',t-1)]=-1
        eq(terms,e0 if t==0 else 0)
        eq({j('ev_served_kw'):1,j('ev_unserved_kw'):1},float(inputs.ev_expected_kw[t]))
        ub({j('ev_served_kw'):1,j('ev_block_limit_kw'):-1},0)
        ub({j('grid_import_kw'):1,j('grid_over_target_kw'):-1},c.grid_target_kw)
        # Net import if actual EV consumption reaches the advertised block limit.
        head={j('grid_import_kw'):1,j('grid_export_kw'):-1,j('ev_block_limit_kw'):1,j('ev_served_kw'):-1}
        ub(head,c.grid_import_max_kw)
        ub({**head,j('grid_over_target_kw'):-1},c.grid_target_kw)
        ub({j('ev_block_limit_kw'):-1,j('ev_q90_headroom_shortfall_kw'):-1},-float(inputs.ev_high_kw[t]))
        ub({j('battery_energy_kwh'):-1,j('reserve_deficit_kwh'):-1},-c.energy_reserve)
        # Local-supply policy: serve free surplus PV to expected EVs; no battery export.
        ub({j('battery_discharge_kw'):1,j('ev_served_kw'):-1},float(inputs.building_kw[t]-solar_load[t]))
    def matrix(rows):
        m=lil_matrix((len(rows),layout.size))
        for r,terms in enumerate(rows):
            for col,v in terms.items():m[r,col]=v
        return m.tocsr()
    return layout,dict(A_eq=matrix(equal),b_eq=np.asarray(rhs),A_ub=matrix(upper),b_ub=np.asarray(limits),bounds=bounds)
