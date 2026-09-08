"""Optional timestamp-checked Series for the unchanged Motor 3 adapter."""
import pandas as pd
import numpy as np
from ..weather.models import ZONE,horizon

def to_motor3(forecast,expected_timestamps):
    expected=pd.DatetimeIndex(expected_timestamps)
    # Existing Motor 3 explicitly requires naive local timestamps.
    if len(expected)!=48 or expected.tz is not None or expected.hasnans:
        raise ValueError('Motor 3 expects 48 naive Sao Paulo local timestamps.')
    canonical=horizon(expected[0])
    if not expected.equals(canonical.tz_localize(None)) or not forecast.data.index.equals(canonical):
        raise ValueError('Solar and Motor 3 horizons differ; no implicit shift.')
    values=forecast.data['solar_previsto_kw'].to_numpy(dtype=float)
    if values.shape!=(48,) or not np.isfinite(values).all() or ((values<0)|(values>125)).any():
        raise ValueError('Solar values outside Motor 3 V1 envelope.')
    return pd.Series(values,index=expected,name='solar_previsto_kw')
