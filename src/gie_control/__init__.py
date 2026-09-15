"""Public integration interface; no UI, network server or hardware driver."""
from .engine import GIEEngine
from .control import GIEControl
from .outputs import standardize

def __getattr__(name):
    if name in ('History','CurrentState'):
        from gie_runtime.models import History,CurrentState
        return {'History':History,'CurrentState':CurrentState}[name]
    if name=='EVSEState':
        from load_balancer.state import EVSEState
        return EVSEState
    raise AttributeError(name)

__all__ = ['GIEEngine', 'GIEControl', 'History', 'CurrentState', 'EVSEState', 'standardize']
