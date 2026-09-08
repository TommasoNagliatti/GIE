from dataclasses import dataclass,field
import numpy as np
import pandas as pd
@dataclass(frozen=True)
class Measurements:
    timestamp:object
    building_kw:float
    ev_kw:float
    solar_kw:float
    grid_import_kw:float=0.
    grid_export_kw:float=0.
@dataclass(frozen=True)
class State:
    battery_soc_pct:float
    previous_charge_kw:float=0.
    previous_discharge_kw:float=0.
@dataclass
class ForecastInputs:
    timestamps:object
    building_kw:object
    ev_expected_kw:object
    ev_high_kw:object
    queue_probability:object
    solar_kw:object
    import_tariff_kwh:object=None # Deprecated compatibility input; not used by objective.
    export_credit_kwh:object=None # Deprecated compatibility input; not used by objective.
    measurements:Measurements|None=None
    provenance:dict=field(default_factory=dict)
    def validated(self,config,state):
        config.validate();ix=pd.DatetimeIndex(pd.to_datetime(self.timestamps))
        if len(ix)!=48 or ix.hasnans or ix.tz is not None or not ix.equals(pd.date_range(ix[0],periods=48,freq='15min')):raise ValueError('48 aligned continuous local timestamps required.')
        if ix[0].minute%15 or ix[0].second or ix[0].microsecond:raise ValueError('Quarter-hour alignment required.')
        self.timestamps=ix
        for key in ('import_tariff_kwh','export_credit_kwh'):
            if getattr(self,key) is None:setattr(self,key,np.zeros(48))
        for key in ['building_kw','ev_expected_kw','ev_high_kw','queue_probability','solar_kw','import_tariff_kwh','export_credit_kwh']:
            a=np.asarray(getattr(self,key),dtype=float)
            if a.shape!=(48,) or not np.isfinite(a).all() or (a<0).any():raise ValueError('Invalid forecast: '+key)
            setattr(self,key,a)
        if (self.ev_expected_kw>config.ev_max_kw).any() or (self.ev_high_kw>config.ev_max_kw).any() or (self.ev_high_kw<self.ev_expected_kw).any():raise ValueError('EV expected/high limits invalid.')
        if (self.solar_kw>config.pv_ac_max_kw).any():raise ValueError('Solar exceeds AC inverter; no implicit curtailment.')
        if (self.queue_probability>1).any():raise ValueError('Invalid probability.')
        if (self.export_credit_kwh>self.import_tariff_kwh).any():raise ValueError('V1 supports nonnegative tariffs with export credit <= import tariff; no arbitrage mode.')
        if not np.isfinite(state.battery_soc_pct) or not config.soc_min_pct<=state.battery_soc_pct<=config.soc_max_pct:raise ValueError('Initial SOC outside absolute limits.')
        if self.measurements is not None:
            if pd.Timestamp(self.measurements.timestamp)!=ix[0]-pd.Timedelta(minutes=15):raise ValueError('Measurements must be latest completed interval.')
            for k in ['building_kw','ev_kw','solar_kw','grid_import_kw','grid_export_kw']:
                v=getattr(self.measurements,k)
                if not np.isfinite(v) or v<0:raise ValueError('Invalid measurement: '+k)
        return self
