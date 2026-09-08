"""Predeclared telemetry disturbances. No decision or setpoint is prescribed."""
LABELS={"building_peak":"Pico de consumo do prédio","ev_peak":"Pico de chegada de EVs","solar_drop":"Redução brusca de geração solar",**{f"fault_{i}":f"Falha EVSE {i}" for i in range(1,5)}}
def inject(state,kind,duration=4):
    if kind not in LABELS:raise ValueError("Unknown telemetry event")
    if not isinstance(duration,int) or not 1<=duration<=16:raise ValueError("Duration 1–16 steps")
    state["events"].append(dict(kind=kind,start=state["index"],end=state["index"]+duration))
def active(state):return [e["kind"] for e in state["events"] if e["start"]<=state["index"]<e["end"]]
# Only for the saved 24-hour validation; UI never injects these automatically.
VALIDATION_EVENTS={32:"building_peak",48:"solar_drop",60:"ev_peak",61:"fault_3"}
