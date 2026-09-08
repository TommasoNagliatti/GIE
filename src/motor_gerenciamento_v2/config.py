from dataclasses import dataclass,asdict
from math import isfinite
from motor_gerenciamento.config import Config as V1Config
@dataclass(frozen=True)
class Config(V1Config):
    battery_capacity_kwh:float=2000.
    battery_charge_max_kw:float=450.
    battery_discharge_max_kw:float=450.
    pv_installed_kwp:float=800.
    pv_ac_max_kw:float=500.
    grid_export_max_kw:float=500.
    reserve_pct:float=0.
    weight_reserve:float=0.
    weight_terminal_reserve:float=0.
    weight_cycle:float=0.
    weight_grid_over:float=0.
    weight_q90_shortfall:float=0.
    weight_grid_import:float=1.
    weight_solar_export:float=0.
    weight_grid_throughput:float=0.
    solver_time_limit_s:float=10.
    def validate(self):
        if self.horizon!=48 or self.step_h!=.25:raise ValueError("48 x 15min required")
        if not 0<=self.soc_min_pct<self.soc_max_pct<=100:raise ValueError("Physical SOC bounds")
        if self.reserve_pct or self.weight_reserve or self.weight_terminal_reserve or self.weight_cycle:raise ValueError("No strategic reserve/cycling penalty in V2")
        if not all(isfinite(v) and v>=0 for v in asdict(self).values()):raise ValueError("Invalid settings")
        if not 0<self.charge_efficiency<=1 or not 0<self.discharge_efficiency<=1:raise ValueError("Efficiency")
        if min(self.battery_capacity_kwh,self.battery_charge_max_kw,self.battery_discharge_max_kw)<=0:raise ValueError("Battery capacity")
        if self.grid_export_max_kw<self.pv_ac_max_kw:raise ValueError("Must-use export capacity")
        if self.ev_max_kw!=self.chargers*self.charger_max_kw:raise ValueError("EV envelope")
        return self
