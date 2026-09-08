"""Public backend: optional fresh telemetry overrides only the executed step."""
import pandas as pd
from .config import Config
from .optimizer import optimize
from .adapters import aligned_inputs
from .dispatch import apply_first
from .events import from_decision,explanation_payload

def run_control(building_forecast,ev_forecast,solar_forecast,import_tariff=None,export_credit=None,state=None,measurements=None,config=None,execution_measurements=None,solver=None):
    if state is None:raise ValueError('Measured battery state is required.')
    c=config or Config()
    inputs=aligned_inputs(building_forecast,ev_forecast,solar_forecast,import_tariff,export_credit,measurements)
    if execution_measurements is not None and pd.Timestamp(execution_measurements.timestamp)!=pd.Timestamp(inputs.timestamps[0]):
        raise ValueError('Execution telemetry must match step zero timestamp.')
    result=optimize(inputs,state,c,solver=solver)
    if execution_measurements is not None and result['execution_allowed']:
        m=execution_measurements
        applied=apply_first(result['first_decision'],state,m.building_kw,m.ev_kw,m.solar_kw,c)
        result['planned_first_decision']=result['first_decision']
        result['first_decision']=applied
        result['execution_uses_current_measurements']=True
        result['events']=from_decision(applied,state,c,result['fallback_used'])
        result['llm_payload']=explanation_payload(result['events'],applied)
        for key in ('battery_charge_kw','battery_discharge_kw','ev_block_limit_kw','grid_import_plan_kw','grid_export_plan_kw','battery_soc_before_pct','battery_soc_after_pct'):
            result[key]=applied[key]
    return result
