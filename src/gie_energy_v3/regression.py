"""Run preserved commercial suites in the existing isolated Phase 3 snapshot."""
import json, os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/energy_v3/v1'
SNAPSHOT=ROOT/'reports/multistation/v1/regression_snapshot'

def main():
    if not (SNAPSHOT/'tools/run_tests.py').is_file():
        raise RuntimeError('Prepare a separate original commercial snapshot first; never overwrite source')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
    ui=os.environ.get('GIE_DEMO_PYTHON',sys.executable)
    rows=[]
    suites=['tests','tests/gie_runtime','tests/motor_gerenciamento','tests/load_balancer','tests/integracoes','tests/observabilidade','tests/high_autonomy_v2','demo/simulation/tests','demo/tests','demo/high_autonomy_v2']
    jobs=[(s,[ui if s.startswith('demo/') and s!='demo/simulation/tests' else sys.executable,'-B','tools/run_tests.py','--suite',s]) for s in suites]
    jobs += [('control',[sys.executable,'-B','-m','unittest','discover','-s','tests/gie_control','-p','test_control.py']),('dashboard',[ui,'-B','-m','unittest','discover','-s','tests/gie_control','-p','test_dashboard.py'])]
    for name,cmd in jobs:
        r=subprocess.run(cmd,cwd=SNAPSHOT,env=env,capture_output=True,text=True,encoding='utf-8')
        (OUT/('regression_'+name.replace('/','_')+'.txt')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
        row={'suite':name,'exit_code':r.returncode}
        try: row.update(json.loads(r.stdout.strip().splitlines()[-1]))
        except (ValueError,IndexError): pass
        rows.append(row);print(row,flush=True)
    (OUT/'regression_results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return int(any(r['exit_code'] for r in rows))

if __name__=='__main__':sys.exit(main())
