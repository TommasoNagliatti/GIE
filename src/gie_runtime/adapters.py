"""Thin calls to existing modules; trained models are loaded once and reused."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from integracoes.weather.models import horizon,STEP
from integracoes.solar.adapter import to_motor3

@dataclass
class Components:
    motor1: object
    motor2: object
    solar: object
    solver: object = None

    @classmethod
    def real(cls,root=None):
        from motor_consumo.predict import MotorHibrido
        from motor_carregadores_v2.predict import MotorCarregadores
        from integracoes.weather.open_meteo import OpenMeteoProvider
        from integracoes.weather.cache import ForecastCache
        from integracoes.solar.forecast import SolarForecaster
        root=Path(root) if root else Path(__file__).resolve().parents[2]
        return cls(MotorHibrido(),MotorCarregadores(),SolarForecaster(OpenMeteoProvider(),ForecastCache(root/'outputs/integracoes/solar_v1/.cache/last_valid_weather.json')))

def history_until(frame,origin):
    frame=frame.copy()
    if 'timestamp' in frame:frame.index=pd.DatetimeIndex(pd.to_datetime(frame.pop('timestamp')))
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is not None:
        raise ValueError('Frozen engines require local naive history timestamps.')
    frame=frame.loc[frame.index<=origin].copy()
    if len(frame)==0 or frame.index.has_duplicates or not frame.index.equals(pd.date_range(frame.index[0],origin,freq='15min')):
        raise ValueError('History must be continuous and end at decision_time minus 15 minutes.')
    return frame

EV_FIELDS=['potencia_solicitada_prevista_kw','potencia_solicitada_alta_kw','energia_solicitada_prevista_kwh',
           'carregadores_ocupados_previstos','carros_chegando_previstos','carros_na_fila_previstos','probabilidade_fila']

def aligned_forecasts(a,b,solar,decision):
    ix=horizon(decision).tz_localize(None)
    for frame,cols in ((a,['consumo_previsto_kw']),(b,EV_FIELDS)):
        times=pd.DatetimeIndex(pd.to_datetime(frame['timestamp_previsto']))
        if not times.equals(ix):raise ValueError('48 forecast timestamps must exactly equal Motor 3 horizon.')
        values=frame[cols].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values<0).any():raise ValueError('Nonfinite or negative forecast.')
    if (b.potencia_solicitada_alta_kw>88).any() or (b.potencia_solicitada_alta_kw<b.potencia_solicitada_prevista_kw).any():raise ValueError('Invalid EV power/Q90.')
    if (b.carregadores_ocupados_previstos>4).any() or (b.probabilidade_fila>1).any():raise ValueError('Invalid occupancy/queue risk.')
    series=to_motor3(solar,ix)
    records=[]
    for j,t in enumerate(ix):
        records.append(dict(timestamp=t,building_kw=float(a.consumo_previsto_kw.iloc[j]),
            **{key:float(b[key].iloc[j]) for key in EV_FIELDS},solar_previsto_kw=float(series.iloc[j])))
    return series,records
