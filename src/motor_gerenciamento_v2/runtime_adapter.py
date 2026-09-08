"""Reuse frozen runtime bytecode with isolated dependency bindings; no global monkeypatch."""
from types import FunctionType
import numpy as np
import pandas as pd
from gie_runtime.orchestrator import run_gie_cycle as original_cycle
from gie_runtime.adapters import aligned_forecasts as original_alignment
from integracoes.weather.models import horizon
from .config import Config
from .policy import run_control

def solar_series(forecast,expected_timestamps):
    ix=pd.DatetimeIndex(expected_timestamps)
    if len(ix)!=48 or ix.tz is not None or not ix.equals(horizon(ix[0]).tz_localize(None)) or not forecast.data.index.equals(horizon(ix[0])):
        raise ValueError("Unaligned V2 solar forecast")
    values=forecast.data.solar_previsto_kw.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<0).any() or (values>500).any():raise ValueError("Solar exceeds V2 AC rating")
    return pd.Series(values,index=ix,name="solar_previsto_kw")

def bind(function,**dependencies):
    scope=dict(function.__globals__);scope.update(dependencies)
    result=FunctionType(function.__code__,scope,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result
# Same orchestration implementation; only the policy and solar envelope are new.
alignment=bind(original_alignment,to_motor3=solar_series)
cycle_impl=bind(original_cycle,aligned_forecasts=alignment,run_control=run_control,Config=Config)
def run_cycle(*args,**kwargs):
    result=cycle_impl(*args,**kwargs)
    result["motor3_version"]="high_autonomy_v2"
    if result.get("management",{}).get("execution_allowed"):
        result["management"]["policy"]="physical_only_solar_charge_lexicographic_import"
    return result
