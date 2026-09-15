"""Lossless wrapper: numerical facts, deterministic prose and display-only state."""
from copy import deepcopy
from time import perf_counter
import json
from .profile import PROFILE
from .messages import messages_for
from .visual import visual_for

MODES = ('NORMAL', 'SIMULATION', 'PRESENTATION', 'MANUAL_DEMO')

def standardize(cycle, mode='NORMAL', provenance=None):
    if mode not in MODES: raise ValueError('Unknown mode')
    start = perf_counter()
    out = deepcopy(cycle)
    cur = out.get('current_state') or {}
    m = out.get('management') or {}
    lb = out.get('load_balancer') or {}
    allowed = bool(m.get('execution_allowed'))
    n = {k:cur.get(k) for k in ('building_kw','solar_kw','battery_soc_pct','ev_demand_kw')}
    for dst,src in {'battery_charge_kw':'battery_charge_kw','battery_discharge_kw':'battery_discharge_kw',
                    'grid_import_kw':'grid_import_plan_kw','grid_export_kw':'grid_export_plan_kw',
                    'ev_block_limit_kw':'ev_block_limit_kw','battery_soc_after_pct':'battery_soc_after_pct',
                    'energy_balance_error_kw':'power_balance_error_kw','ev_unserved_kw':'current_ev_unserved_total_kw'}.items():
        n[dst] = m.get(src) if allowed else None
    n['ev_served_kw'] = (m.get('first_decision') or {}).get('ev_served_kw') if allowed else None
    n['evse_setpoints_kw'] = [lb.get(f'evse_{i}_kw') if allowed else None for i in range(1,5)]
    source_devices = {e['evse_id']:e for e in cur.get('evses',[])}
    n['evses'] = {f'EVSE{i}':deepcopy(lb.get(f'EVSE{i}',source_devices.get(f'EVSE{i}',{}))) for i in range(1,5)}
    out.update(output_version='1.0',timestamp=out['decision_time'],profile=PROFILE,mode=mode,
               numeric_state=n,execution_allowed=allowed,provenance=deepcopy(provenance or {}))
    out['messages'] = messages_for(out)
    out['primary_message'] = out['messages'][0]
    out['reason_codes'] = sorted({code for msg in out['messages'] for code in msg['reason_codes']} |
                                 {e['code'] for e in out.get('events',[])})
    out['visual_state'] = visual_for(out)
    out['maquette_state'] = deepcopy(out['visual_state'])
    out['presentation_metadata'] = {'llm_calls':0,'setpoints_are_limits':True,'hardware_commands_sent':False,
                                    'explanation_basis':'Measured values, applied decision and native events; no solver causal attribution.'}
    out['output_elapsed_ms'] = (perf_counter()-start)*1000
    json.dumps(out,allow_nan=False)
    return out
