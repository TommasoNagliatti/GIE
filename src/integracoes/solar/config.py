from dataclasses import dataclass, field
from math import isfinite
from ..weather.models import WeatherSite

@dataclass(frozen=True)
class SolarConfig:
    site: WeatherSite = field(default_factory=WeatherSite)
    installed_kwp: float = 150.0
    inverter_ac_kw: float = 125.0
    performance_ratio: float = 0.82
    cache_max_age_hours: float = 3.0

    def validate(self):
        self.site.validate()
        if not all(isfinite(v) for v in (self.installed_kwp,self.inverter_ac_kw,self.performance_ratio,self.cache_max_age_hours)):
            raise ValueError('Nonfinite solar configuration.')
        if not (self.installed_kwp>0 and self.inverter_ac_kw>0 and 0<self.performance_ratio<=1 and 0<self.cache_max_age_hours<=12):
            raise ValueError('Invalid PV settings/cache age.')
        return self
