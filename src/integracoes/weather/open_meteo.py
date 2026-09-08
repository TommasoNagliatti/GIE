"""Official Forecast API; one bounded request, no client interpolation."""
import json
from urllib.parse import urlencode
from urllib.request import urlopen
import pandas as pd
from .provider import WeatherProvider
from .models import WeatherBatch, COLUMNS, STEP, horizon

VARIABLES = ['global_tilted_irradiance','shortwave_radiation','direct_normal_irradiance',
             'temperature_2m','relative_humidity_2m','cloud_cover']
UNITS = ['W/m²','W/m²','W/m²','°C','%','%']

class OpenMeteoProvider(WeatherProvider):
    name = 'open_meteo'
    endpoint = 'https://api.open-meteo.com/v1/forecast'

    def __init__(self, timeout_seconds=10.0, transport=None, clock=None):
        if not 0 < timeout_seconds <= 60:
            raise ValueError('Timeout must be in (0,60] seconds.')
        self.timeout_seconds=timeout_seconds
        self.transport=transport or self._get_json
        self.clock=clock or (lambda:pd.Timestamp.now(tz='UTC'))
        self.last_url=None
        self.last_response=None

    @staticmethod
    def _get_json(url, timeout):
        with urlopen(url,timeout=timeout) as response:
            return json.load(response)

    def parameters(self,start,site,periods=96):
        site.validate()
        ix=horizon(start,periods)
        return dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone,
                    tilt=site.tilt,azimuth=site.azimuth,minutely_15=','.join(VARIABLES),
                    temperature_unit='celsius',timeformat='unixtime',
                    start_minutely_15=ix[0].strftime('%Y-%m-%dT%H:%M'),
                    end_minutely_15=(ix[-1]+STEP).strftime('%Y-%m-%dT%H:%M'))

    def fetch(self,start,site,periods=96):
        params=self.parameters(start,site,periods)
        self.last_url=self.endpoint+'?'+urlencode(params)
        called_at=self.clock()
        raw=self.transport(self.last_url,self.timeout_seconds)
        self.last_response=raw
        ix=horizon(start,periods)
        if raw.get('timezone')!=site.timezone:
            raise ValueError('Unexpected API timezone.')
        if raw.get('utc_offset_seconds')!=int(ix[0].utcoffset().total_seconds()):
            raise ValueError('Unexpected API UTC offset.')
        units=raw['minutely_15_units']
        if units.get('time')!='unixtime' or any(units.get(v)!=u for v,u in zip(VARIABLES,UNITS)):
            raise ValueError('Unexpected API units.')
        block=raw['minutely_15']
        api_ix=pd.to_datetime(block['time'],unit='s',utc=True).tz_convert(site.timezone)
        expected=horizon(start,periods+1)
        if not api_ix.equals(expected):
            raise ValueError('API timeline incomplete, duplicated or not aligned.')
        source=pd.DataFrame({v:block[v] for v in VARIABLES},index=api_ix)
        if source.isna().any().any():
            raise ValueError('API returned missing values.')
        data=pd.DataFrame(index=ix)
        for j,(v,col) in enumerate(zip(VARIABLES,COLUMNS)):
            # Radiation stamped 08:15 represents [08:00,08:15).
            # Instantaneous weather stamped 08:00 remains at 08:00.
            lookup=ix+STEP if j<3 else ix
            data[col]=source.loc[lookup,v].to_numpy(dtype=float)
        meta=dict(provider=self.name,url=self.last_url,parameters=params,called_at=str(called_at),
                  timestamp_semantics='interval_start',radiation_semantics='mean_over_[timestamp,timestamp+15min)',
                  radiation_api_label='interval_end',instant_weather_semantics='at_interval_start',
                  server_interpolation='Open-Meteo interpolates hourly to 15 minutes outside native regions',
                  client_interpolation=False,grid_latitude=raw.get('latitude'),grid_longitude=raw.get('longitude'),
                  attribution='Weather data by Open-Meteo.com, CC BY 4.0')
        return WeatherBatch(data,pd.Timestamp(called_at),meta,raw).validate()
