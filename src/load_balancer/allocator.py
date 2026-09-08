"""Deterministic max-min water filling; no ML, SOC or network calls."""
from itertools import combinations
from math import fsum, isfinite
from .state import as_datetime

def water_fill(caps, budget, floors=None):
    """Maximize the smallest power first, respecting optional admitted floors."""
    floors = floors or [0.0] * len(caps)
    if max(sum(caps), fsum(caps)) <= budget:
        return list(caps)
    low, high = 0.0, max(caps, default=0.0)
    # The lower endpoint is always feasible; no upward rounding of commands.
    for _ in range(80):
        mid = (low + high) / 2
        powers = [max(f, min(cap, mid)) for cap, f in zip(caps, floors)]
        if max(sum(powers), fsum(powers)) <= budget:
            low = mid
        else:
            high = mid
    return [max(f, min(cap, low)) for cap, f in zip(caps, floors)]

def allocate(block_kw, evses, timestamp, config, cycle=0):
    config.validate()
    if not isfinite(block_kw) or not 0 <= block_kw <= config.block_max_kw:
        raise ValueError('Block must be finite and between 0 and 88 kW.')
    timestamp = as_datetime(timestamp)
    devices = {e.evse_id: e for e in evses}
    if len(evses) != 4 or set(devices) != set(config.evse_ids):
        raise ValueError('Provide each of the four EVSEs exactly once.')
    caps, ages = {}, {}
    for id, e in devices.items():
        if type(e.connected) is not bool or e.state not in {'available', 'charging', 'suspended', 'fault', 'offline'}:
            raise ValueError('Invalid connection/status.')
        values = [e.max_power_kw] + ([] if e.vehicle_max_kw is None else [e.vehicle_max_kw])
        if any(not isfinite(v) or v < 0 for v in values):
            raise ValueError('Invalid reported power capability.')
        age = 0.0
        if e.connected_since is not None:
            age = (timestamp - as_datetime(e.connected_since)).total_seconds()
            if age < 0:
                raise ValueError('Session start cannot be in the future.')
        ages[id] = age
        caps[id] = min(config.evse_max_kw, *values) if e.connected and e.state in {'available', 'charging'} else 0.0
    ids = list(config.evse_ids)
    floors = config.minimum_kw
    active = [id for id in ids if caps[id] > 0 and floors.get(id, 0) <= caps[id]]
    allocation = {id: 0.0 for id in ids}
    if not any(floors.get(id, 0) for id in active):
        allocation.update(zip(active, water_fill([caps[id] for id in active], block_kw)))
    else:
        # At most 16 subsets. Minimum-on hardware constraints make admission
        # discrete. Max-min is applied to the full four-power vector, including
        # zero for non-admitted devices. Arrival time only breaks exact ties.
        rotated = ids[cycle % 4:] + ids[:cycle % 4]
        best = None
        for size in range(len(active) + 1):
            for subset in combinations(active, size):
                minimums = [floors.get(id, 0.0) for id in subset]
                if fsum(minimums) > block_kw:
                    continue
                candidate = {id: 0.0 for id in ids}
                candidate.update(zip(subset, water_fill([caps[id] for id in subset], block_kw, minimums)))
                key = (tuple(sorted(candidate.values())), tuple(sorted((ages[id] for id in subset), reverse=True)), tuple(id in subset for id in rotated))
                if best is None or key > best:
                    best, allocation = key, candidate
    assert fsum(allocation.values()) <= block_kw
    assert all(0 <= allocation[id] <= caps[id] for id in ids)
    return caps, allocation
