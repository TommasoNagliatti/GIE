"""Simple GTI model with API -> fresh-enough cache -> zero generation."""
from dataclasses import asdict
import numpy as np
import pandas as pd
from .config import SolarConfig
from .models import SolarForecast
from ..weather.models import horizon,COLUMNS

def irradiance_to_power(gti,config):
    config.validate()
    values=np.asarray(gti,dtype=float)
    if not np.isfinite(values).all():raise ValueError('GTI must be finite.')
    return np.clip(config.installed_kwp*values/1000*config.performance_ratio,0,config.inverter_ac_kw)

class SolarForecaster:
    def __init__(self,provider,cache,config=None,clock=None):
        self.provider=provider;self.cache=cache
        self.config=(config or SolarConfig()).validate()
        self.clock=clock or (lambda:pd.Timestamp.now(tz='UTC'))

    def forecast(self,decision_time):
        ix=horizon(decision_time)
        now=pd.Timestamp(self.clock())
        if now.tzinfo is None:raise ValueError('Clock must be timezone aware.')
        key=dict(schema=1,provider=self.provider.name,site=asdict(self.config.site))
        diagnostics=[];batch=None;source='fallback';stale=True
        try:
            batch=self.provider.fetch(ix[0],self.config.site,periods=96)
            data=batch.select(ix)
            age=(now-batch.fetched_at).total_seconds()
            # A request's fetch timestamp may be milliseconds after service entry.
            if not -60 <= age <= self.config.cache_max_age_hours*3600:
                raise ValueError('Provider returned an expired forecast.')
            source=self.provider.name;stale=False
            try:self.cache.save(batch,key)
            except Exception as e:diagnostics.append('cache_write: '+type(e).__name__+': '+str(e))
        except Exception as e:
            diagnostics.append('provider: '+type(e).__name__+': '+str(e))
            batch=None
            try:
                batch=self.cache.load(key,now,self.config.cache_max_age_hours)
                data=batch.select(ix)
                source='cache';stale=True
            except Exception as cached_error:
                diagnostics.append('cache: '+type(cached_error).__name__+': '+str(cached_error))
                batch=None
                data=pd.DataFrame(np.nan,index=ix,columns=COLUMNS)
        data['solar_previsto_kw']=0.0 if batch is None else irradiance_to_power(data[COLUMNS[0]],self.config)
        data.index.name='timestamp'
        meta=dict(decision_time=ix[0].isoformat(),service_called_at=now.isoformat(),
                  fetched_at=None if batch is None else batch.fetched_at.isoformat(),
                  config=asdict(self.config),diagnostics=diagnostics,
                  weather={} if batch is None else batch.metadata,
                  current_solar_telemetry_overridden=False,
                  fallback_weather_values='null (unknown); only solar power is forced to zero')
        return SolarForecast(data,source,stale,meta)
