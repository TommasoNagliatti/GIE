"""Local structured events. Connection/fault events are transition-based."""
def create_events(timestamp, devices, requested, allocated, block, previous):
    events = []
    def add(code, id=None, **context):
        events.append(dict(timestamp=timestamp, code=code, evse_id=id, severity='warning' if code == 'EVSE_FAULT' else 'info', context=context))
    for e in devices:
        id = e.evse_id
        was = previous.previous_connected.get(id, False)
        if e.connected and not was:
            add('EVSE_CONNECTED', id)
        if not e.connected and was:
            add('EVSE_DISCONNECTED', id)
        if e.state == 'fault' and previous.previous_status.get(id) != 'fault':
            add('EVSE_FAULT', id)
        if requested[id] - allocated[id] > 1e-9:
            add('EVSE_POWER_LIMITED', id, requested_kw=requested[id], allocated_kw=allocated[id])
    if block > 0 and abs(sum(allocated.values()) - block) <= 1e-9:
        add('EV_BLOCK_FULLY_ALLOCATED', block_kw=block)
    return events
