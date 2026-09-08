"""Provider-independent weather contract: local interval-start timestamps."""
from dataclasses import dataclass, asdict, field
from math import isfinite
import pandas as pd
import numpy as np

ZONE = 'America/Sao_Paulo'
STEP = pd.Timedelta(minutes=15)
COLUMNS = ['global_tilted_irradiance_wm2','shortwave_radiation_wm2','direct_normal_irradiance_wm2',
           'temperature_c','relative_humidity_pct','cloud_cover_pct']

def local_time(value):
    t = pd.Timestamp(value)
    if pd.isna(t):
        raise ValueError('Missing timestamp.')
    return t.tz_localize(ZONE) if t.tzinfo is None else t.tz_convert(ZONE)

def horizon(start, periods=48):
    start = local_time(start)
    if start.minute % 15 or start.second or start.microsecond or start.nanosecond:
        raise ValueError('Decision time must be an exact quarter hour; no implicit rounding.')
    return pd.date_range(start, periods=periods, freq='15min')

@dataclass(frozen=True)
class WeatherSite:
    latitude: float = -23.5740619
    longitude: float = -46.6231674
    timezone: str = ZONE
    tilt: float = 23.0
    azimuth: float = 180.0

    def validate(self):
        if self.timezone != ZONE:
            raise ValueError('V1 expects America/Sao_Paulo.')
        if not all(isfinite(v) for v in (self.latitude,self.longitude,self.tilt,self.azimuth)):
            raise ValueError('Nonfinite site configuration.')
        if not (-90<=self.latitude<=90 and -180<=self.longitude<=180 and 0<=self.tilt<=90 and -180<=self.azimuth<=180):
            raise ValueError('Invalid location/orientation.')
        return self

@dataclass
class WeatherBatch:
    data: pd.DataFrame
    fetched_at: pd.Timestamp
    metadata: dict = field(default_factory=dict)
    raw_response: dict | None = None

    def validate(self):
        ix = self.data.index
        if not isinstance(ix,pd.DatetimeIndex) or len(ix)<48 or str(ix.tz)!=ZONE or ix.hasnans:
            raise ValueError('Invalid weather time index.')
        if not ix.equals(horizon(ix[0],len(ix))):
            raise ValueError('Weather must have continuous unique 15-minute interval starts.')
        values = self.data[COLUMNS].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values[:,:3]<0).any():
            raise ValueError('Missing/nonfinite/negative weather data.')
        if ((values[:,4:]<0)|(values[:,4:]>100)).any():
            raise ValueError('Humidity/cloud cover outside 0–100%.')
        if pd.isna(self.fetched_at) or self.fetched_at.tzinfo is None:
            raise ValueError('Fetch time must include timezone.')
        return self

    def select(self, ix):
        self.validate()
        if not ix.isin(self.data.index).all():
            raise ValueError('Weather does not cover all 48 requested intervals.')
        return self.data.loc[ix,COLUMNS].copy()
