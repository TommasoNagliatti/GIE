"""Physical settings and predeclared objective weights; no test-period tuning."""
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class Config:
    horizon:int=48
    step_h:float=.25
    battery_capacity_kwh:float=200.
    battery_charge_max_kw:float=100.
    battery_discharge_max_kw:float=100.
    charge_efficiency:float=.95
    discharge_efficiency:float=.95
    soc_min_pct:float=20.
    soc_max_pct:float=95.
    reserve_pct:float=30.
    ev_max_kw:float=88.
    chargers:int=4
    charger_max_kw:float=22.
    pv_installed_kwp:float=150.
    pv_ac_max_kw:float=125.
    grid_target_kw:float=300.
    grid_import_max_kw:float=350.
    grid_export_max_kw:float=150.
    # Dimensionless engineering penalties, not prices or billing rates.
    weight_grid_import:float=.10
    weight_solar_export:float=.05
    weight_grid_over:float=1000. # per kWh above operational target
    weight_ev_unserved:float=100. # per kWh; multiplied by (1+queue probability)
    weight_q90_shortfall:float=10. # per kWh of reserved headroom shortfall
    weight_reserve:float=2. # per kWh deficit per hour
    weight_terminal_reserve:float=5. # per kWh deficit at end
    weight_cycle:float=.04 # per kWh charged/discharged
    weight_grid_throughput:float=.001 # removes zero-spread import/export degeneracy
    solver_time_limit_s:float=3.
    tolerance:float=1e-5
    simultaneity_kw:float=1e-5
    @property
    def energy_min(self):return self.battery_capacity_kwh*self.soc_min_pct/100
    @property
    def energy_max(self):return self.battery_capacity_kwh*self.soc_max_pct/100
    @property
    def energy_reserve(self):return self.battery_capacity_kwh*self.reserve_pct/100
    def validate(self):
        if self.horizon!=48 or self.step_h!=.25:raise ValueError('V1 requires 48 x 15-minute intervals.')
        if not 0<=self.soc_min_pct<self.reserve_pct<=self.soc_max_pct<=100:raise ValueError('Invalid SOC limits.')
        if not 0<self.charge_efficiency<=1 or not 0<self.discharge_efficiency<=1:raise ValueError('Invalid efficiencies.')
        if not 0<self.grid_target_kw<=self.grid_import_max_kw or self.grid_export_max_kw<self.pv_ac_max_kw:raise ValueError('Invalid grid limits.')
        if self.ev_max_kw!=self.chargers*self.charger_max_kw:raise ValueError('Invalid EV block capacity.')
        for k,v in asdict(self).items():
            if not isinstance(v,(int,float)) or v<0:raise ValueError('Invalid configuration: '+k)
        if min(self.battery_capacity_kwh,self.weight_cycle,self.weight_grid_throughput,self.solver_time_limit_s)<=0:raise ValueError('Positive settings required.')
        return self
