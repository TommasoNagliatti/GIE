"""Public pure local entry point: result plus state for the next cycle."""
from math import fsum
from .config import Config
from .state import BalancerState, as_datetime
from .allocator import allocate
from .events import create_events

def run_balancer(ev_block_limit_kw, evses, timestamp, previous=None, config=None):
    config = config or Config()
    previous = previous or BalancerState()
    evses = list(evses)
    requested, allocated = allocate(ev_block_limit_kw, evses, timestamp, config, previous.cycle)
    timestamp = as_datetime(timestamp).isoformat()
    by_id = {e.evse_id: e for e in evses}
    result = dict(timestamp=timestamp, ev_block_limit_kw=ev_block_limit_kw,
                  requested_total_kw=fsum(requested.values()), allocated_total_kw=fsum(allocated.values()))
    for i, id in enumerate(config.evse_ids, 1):
        e = by_id[id]
        result[f'evse_{i}_kw'] = allocated[id]
        result[id] = dict(state=e.state, connected=e.connected, requested_kw=requested[id], allocated_kw=allocated[id],
                          reported_evse_max_kw=e.max_power_kw, vehicle_max_kw=e.vehicle_max_kw,
                          minimum_kw=config.minimum_kw.get(id, 0.0), connected_since=None if e.connected_since is None else as_datetime(e.connected_since).isoformat())
    result['events'] = create_events(timestamp, [by_id[id] for id in config.evse_ids], requested, allocated, ev_block_limit_kw, previous)
    next_state = BalancerState({e.evse_id: e.connected for e in evses}, {e.evse_id: e.state for e in evses}, previous.cycle + 1)
    return result, next_state
