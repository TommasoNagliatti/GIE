"""Physical envelope; optional minimum power is configured per EVSE."""
from dataclasses import dataclass, field
from math import isfinite

@dataclass(frozen=True)
class Config:
    evse_ids: tuple[str, ...] = ('EVSE1', 'EVSE2', 'EVSE3', 'EVSE4')
    evse_max_kw: float = 22.0
    block_max_kw: float = 88.0
    minimum_kw: dict[str, float] = field(default_factory=dict)

    def validate(self):
        if self.evse_ids != ('EVSE1', 'EVSE2', 'EVSE3', 'EVSE4'):
            raise ValueError('V1 requires EVSE1 through EVSE4.')
        if self.evse_max_kw != 22 or self.block_max_kw != 88:
            raise ValueError('V1 physical envelope is four 22 kW EVSEs.')
        if set(self.minimum_kw) - set(self.evse_ids):
            raise ValueError('Unknown EVSE in minimum_kw.')
        if any(not isfinite(v) or not 0 <= v <= 22 for v in self.minimum_kw.values()):
            raise ValueError('Invalid configured minimum power.')
        return self
