from time import perf_counter
from scipy.optimize import linprog
from .config import Config
from .constraints import build,NAMES
from .objective import build_objective
from .validation import validate_plan,MaterialSimultaneityError,PhysicalInfeasibleError
from .fallback import greedy_plan
from .flow_allocator import allocate
from .events import from_decision,explanation_payload,make_event
def optimize(inputs,state,config=None,solver=None):
    c=config or Config();inputs.validated(c,state)
    layout,problem=build(inputs,state,c);cost=build_objective(layout,inputs,c)
    start=perf_counter();fallback=False;reason=None;objective=None;status='optimal'
    try:
        result=(solver or linprog)(cost,**problem,method='highs',options={'time_limit':c.solver_time_limit_s,'primal_feasibility_tolerance':1e-7,'dual_feasibility_tolerance':1e-7})
        solver_ms=(perf_counter()-start)*1000
        if not result.success:raise RuntimeError(f'HiGHS status {result.status}: {result.message}')
        values={name:layout.series(result.x,name) for name in NAMES};plan=[];before=state.battery_soc_pct
        for t in range(c.horizon):
            row={name:float(a[t]) for name,a in values.items()}
            row.update(timestamp=str(inputs.timestamps[t]),building_kw=float(inputs.building_kw[t]),ev_expected_kw=float(inputs.ev_expected_kw[t]),ev_high_kw=float(inputs.ev_high_kw[t]),
                solar_disponivel_kw=float(inputs.solar_kw[t]),solar_utilizado_kw=float(inputs.solar_kw[t]),battery_soc_before_pct=before,
                battery_soc_after_pct=row['battery_energy_kwh']/c.battery_capacity_kwh*100)
            row['grid_import_plan_kw']=row.pop('grid_import_kw');row['grid_export_plan_kw']=row.pop('grid_export_kw')
            row['grid_capacity_over_target_kw']=row['grid_over_target_kw']
            row['grid_over_target_kw']=max(0,row['grid_import_plan_kw']-c.grid_target_kw)
            before=row['battery_soc_after_pct'];plan.append(row)
        audit=validate_plan(plan,state,c);objective=float(result.fun)
    except MaterialSimultaneityError:
        raise # Explicit stop required; never silently switch formulation or MILP.
    except Exception as exc:
        solver_ms=(perf_counter()-start)*1000;fallback=True;reason=str(exc);status='fallback'
        try:plan=greedy_plan(inputs,state,c);audit=validate_plan(plan,state,c)
        except PhysicalInfeasibleError as impossible:
            event=make_event('PHYSICALLY_INFEASIBLE','critical',str(impossible),inputs.timestamps[0],{'solver_error':reason})
            return {'decision_time':str(inputs.timestamps[0]),'solver_status':'physically_infeasible','solver_runtime_ms':solver_ms,
                    'fallback_used':True,'execution_allowed':False,'fallback_reason':str(impossible),'plan':[],'events':[event],
                    'llm_payload':{'event_codes':['PHYSICALLY_INFEASIBLE'],'reason':str(impossible),'api_called':False}}
    for row in plan:row['flows']=allocate(row,c.tolerance)
    first=plan[0];events=from_decision(first,state,c,fallback)
    answer={'decision_time':str(inputs.timestamps[0]),'solver_status':status,'solver_runtime_ms':solver_ms,'fallback_used':fallback,
            'fallback_reason':reason,'execution_allowed':True,'objective_value':objective,'plan':plan,'first_decision':first,
            'events':events,'llm_payload':explanation_payload(events,first),'validation':audit,'provenance':inputs.provenance}
    for name in ['battery_charge_kw','battery_discharge_kw','ev_block_limit_kw','grid_import_plan_kw','grid_export_plan_kw','battery_soc_before_pct','battery_soc_after_pct']:answer[name]=first[name]
    answer['controller_runtime_ms']=(perf_counter()-start)*1000
    return answer

