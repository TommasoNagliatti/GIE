"""Run core in its existing venv; keep SciPy/ML out of the optional UI env."""
from pathlib import Path
from dataclasses import asdict
import subprocess,os,json

def run_demo(source,root=None,previous=None):
    root=Path(root or Path(__file__).resolve().parents[2])
    python=root/'.venv/Scripts/python.exe'
    program='''import sys,json
from gie_control.scenarios import execute_demo
from load_balancer.state import BalancerState
d=json.load(sys.stdin)
p=BalancerState(**d['previous']) if d['previous'] else None
print(json.dumps(execute_demo(d['source'],previous=p),ensure_ascii=False,allow_nan=False))
'''
    env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    result=subprocess.run([str(python),'-B','-c',program],input=json.dumps({'source':source,'previous':asdict(previous) if previous else None}),
              text=True,encoding='utf-8',capture_output=True,cwd=root,env=env,timeout=90,
              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Core demo failed: '+result.stderr[-2000:])
    return json.loads(result.stdout)
