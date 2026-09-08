"""Optional decorator around the frozen runtime; no dependency on the demo."""
from copy import deepcopy
from .trace import build_trace

def observe_cycle(cycle,previous=None,logger=None,include_llm_context=True):
    result=deepcopy(cycle)
    trace=build_trace(result,previous,include_llm_context)
    if logger is not None:
        try:logger.append(trace)
        except Exception as e:
            trace['logging_error']={'type':type(e).__name__,'message':str(e)}
    result['decision_trace']=trace
    if include_llm_context:result['llm_context']=trace['llm_context']
    return result

def run_observed_cycle(*args,previous_trace=None,logger=None,include_llm_context=True,**kwargs):
    from gie_runtime import run_gie_cycle
    return observe_cycle(run_gie_cycle(*args,**kwargs),previous_trace,logger,include_llm_context)
