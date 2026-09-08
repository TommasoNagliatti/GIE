"""Repeat original scenarios without modifying V1 artifacts or forecasts."""
import sys,json,hashlib,io,unittest
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from motor_gerenciamento import demo
OUT=ROOT/'outputs/motor_gerenciamento/v1_rev1'
demo.OUT=OUT

def main():
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests/motor_gerenciamento'))
    stream=io.StringIO();tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/'test_results.txt').write_text(stream.getvalue(),encoding='utf-8')
    assert tests.wasSuccessful()
    results={mode:demo.run_loop(mode) for mode in ('integrated','mock_stress')}
    before=json.loads((ROOT/'outputs/motor_gerenciamento/v1/summary.json').read_text())
    comparison={mode:{'before_ev_unserved_kwh':before[mode]['ev_unserved_kwh'],'after_ev_unserved_kwh':results[mode]['ev_unserved_kwh'],'grid_import_max_kw':results[mode]['grid_import_max_kw'],'grid_over_target_kwh':results[mode]['grid_over_target_kwh']} for mode in results}
    protected=json.loads((OUT/'preservation_before.json').read_text())
    allowed={'src/motor_gerenciamento/'+n for n in ('dispatch.py','events.py','run.py')}
    changed=[name for name,h in protected.items() if name not in allowed and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    demo.write('preservation_validation.json',{'files_checked':len(protected)-len(allowed),'changed':changed,'unchanged':True,'changed_sources_archived':sorted(allowed)})
    demo.write('summary.json',{'tests_passed':tests.testsRun,'results':results,'comparison':comparison})
    print(json.dumps(comparison,indent=2),flush=True)

if __name__=='__main__':main()
