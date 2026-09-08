from time import perf_counter

def initial_health():
    return {name:dict(status='skipped',elapsed_ms=0.0) for name in ('validation','motor1','motor2','solar','alignment','motor3','load_balancer')}

def timed(health,name,call):
    start=perf_counter()
    try:
        value=call()
        health[name]['status']='ok'
        return value
    except Exception as e:
        health[name].update(status='error',error_type=type(e).__name__,error=str(e))
        raise
    finally:health[name]['elapsed_ms']+=(perf_counter()-start)*1000
