from dataclasses import dataclass,field,asdict,is_dataclass
from datetime import datetime
import math
import numpy as np
import pandas as pd

@dataclass
class History:
    building: pd.DataFrame
    ev: pd.DataFrame
    provenance: dict = field(default_factory=dict)

@dataclass
class CurrentState:
    timestamp: object
    building_kw: float
    ev_demand_kw: float
    solar_kw: float
    battery_soc_pct: float
    evses: list
    previous_charge_kw: float = 0.0
    previous_discharge_kw: float = 0.0
    provenance: dict = field(default_factory=dict)

def json_safe(value):
    if is_dataclass(value):return json_safe(asdict(value))
    if isinstance(value,dict):return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [json_safe(v) for v in value]
    if isinstance(value,(pd.Timestamp,datetime)):return value.isoformat()
    if isinstance(value,np.generic):return json_safe(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    return value
