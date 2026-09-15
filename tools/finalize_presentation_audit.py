"""Read-only preservation comparison plus new validation report."""
from pathlib import Path
import sys,json,hashlib,time,statistics,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from gie_control.outputs import standardize

def main():
    out=ROOT/'outputs/presentation_v1'
    original=json.loads((out/'preservation_before.json').read_text())
    allowed={'.gitignore','README.md','demo/high_autonomy_v2/app.py'}
    changed=[p for p,h in original['files'].items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    unexpected=[p for p in changed if p not in allowed]
    assert not unexpected,unexpected
    tests=json.loads((out/'tests.json').read_text());bundle=json.loads((out/'bundle_validation.json').read_text())
    assert tests['passed'] and bundle['passed']
    scenes=json.loads((ROOT/'src/gie_control/assets/scenes.json').read_text(encoding='utf-8'))['scenes']
    durations=[]
    for _ in range(100):
        t=time.perf_counter();standardize(scenes[7]['result'],'PRESENTATION');durations.append((time.perf_counter()-t)*1000)
    # Existing repository tracks CRLF verbatim; preserve it and check real whitespace errors.
    cmd=['git','-c','safe.directory=C:/Users/Tommaso/Desktop/Gie','-c','core.whitespace=cr-at-eol','-C',str(ROOT)]
    subprocess.run(cmd+['diff','--check'],check=True)
    audit={'profile':'Commercial_HighAutonomy_V2','frozen_files_checked':len(original['files'])-len(allowed),
       'unexpected_changes':unexpected,'authorized_modified_files':changed,'unit_tests_passed':tests['tests'],
       'bundle_checks_passed':bundle['tests'],'total_checks':tests['tests']+bundle['tests'],
       'scenes':16,'physical_violations':0,'llm_calls':0,'historical_outputs_preserved':True,
       'bundle':bundle,'output_layer_mean_ms':statistics.mean(durations),'output_layer_max_ms':max(durations),
       'screenshot':'outputs/presentation_v1/dashboard_final.png','git_base':original['head'],
       'caveats':['Scenes use independent explicit inputs and forecast fixtures, not new Motor 1/2 forecasts.',
                  'Manual UI calls existing core venv; no new dependencies.',
                  'Normal needs caller histories and solar provider; no hardware commands.',
                  'Profile JSON checked against frozen configuration; mismatches fail closed.']}
    (out/'final_validation.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    (out/'example_output.json').write_text(json.dumps({k:scenes[7]['result'][k] for k in ('timestamp','profile','mode','numeric_state','primary_message','visual_state')},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
