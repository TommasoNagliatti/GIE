"""Run untouched legacy suites in an isolated snapshot, never writing old outputs."""
import io,json,os,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/station_forecasts/v1'
copy=OUT/'regression_snapshot';copy.mkdir(exist_ok=True)
blob=subprocess.check_output(['git','archive','--format=zip','HEAD'],cwd=ROOT)
with zipfile.ZipFile(io.BytesIO(blob)) as z:
    for name in z.namelist():
        target=(copy/name).resolve()
        assert target.is_relative_to(copy.resolve())
    z.extractall(copy)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
python=os.sys.executable
summary=[]
for suite in [None,'tests','tests/gie_runtime','tests/motor_gerenciamento','tests/load_balancer','tests/integracoes','tests/observabilidade','tests/high_autonomy_v2','demo/simulation/tests','demo/tests','demo/high_autonomy_v2']:
    cmd=[python,'-B',str(copy/'tools/run_tests.py')]
    if suite:cmd+=['--suite',suite]
    result=subprocess.run(cmd,cwd=copy,capture_output=True,text=True,encoding='utf-8',env=env)
    name=(suite or 'release_runner').replace('/','_')
    (OUT/f'regression_{name}.txt').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    row=dict(suite=suite or 'release_runner',exit_code=result.returncode)
    try:row.update(json.loads(result.stdout.strip().splitlines()[-1]))
    except (ValueError,IndexError):pass
    summary.append(row);print(row,flush=True)
(OUT/'regression_results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
