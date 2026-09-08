"""Measured EVSE inputs and optional previous-cycle state for events/ties."""
from dataclasses import dataclass, field
from datetime import datetime

def as_datetime(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))

@dataclass(frozen=True)
class EVSEState:
    evse_id: str
    connected: bool = False
    state: str = 'available'
    max_power_kw: float = 22.0
    vehicle_max_kw: float | None = None
    connected_since: str | datetime | None = None

@dataclass
class BalancerState:
    previous_connected: dict[str, bool] = field(default_factory=dict)
    previous_status: dict[str, str] = field(default_factory=dict)
    cycle: int = 0
