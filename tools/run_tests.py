"""Portable release checks; no training, network requests or full-day reruns."""
import argparse,hashlib,json,os,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);sys.path[:0]=[str(ROOT),str(ROOT/'src')]
def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item
def main():
    p=argparse.ArgumentParser();p.add_argument('--demo',action='store_true');p.add_argument('--suite');a=p.parse_args()
    if a.suite:
        if a.suite=='tests':
            import importlib.util
            tests=[]
            for f in sorted((ROOT/'tests').glob('test*.py')):
                spec=importlib.util.spec_from_file_location(f.stem,f);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
                tests.extend(flatten(unittest.TestLoader().loadTestsFromModule(mod)))
        else:tests=list(flatten(unittest.TestLoader().discover(a.suite,pattern='test*.py')))
        for t in tests:
            if (a.suite,t._testMethodName) in {('tests/high_autonomy_v2','test_14_preservation'),('tests/observabilidade','test_frozen'),('demo/simulation/tests','test_preservation')}:
                # Historical full-disk snapshot includes intentionally private archives.
                setattr(type(t),t._testMethodName,unittest.skip('Historical local archive check; portable frozen manifest checked by release runner.')(getattr(type(t),t._testMethodName)))
        r=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(tests))
        print(json.dumps({'suite':a.suite,'run':r.testsRun,'passed':r.testsRun-len(r.failures)-len(r.errors)-len(r.skipped),'skipped':len(r.skipped),'success':r.wasSuccessful()}))
        return 0 if r.wasSuccessful() else 1
    manifest=json.loads((ROOT/'docs/release/frozen_manifest.json').read_text(encoding='utf-8'))
    changed=[n for n,h in manifest.items() if not (ROOT/n).is_file() or hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h]
    if changed:raise RuntimeError('Frozen file mismatch: '+repr(changed))
    suites=['demo/tests','demo/high_autonomy_v2'] if a.demo else ['tests','tests/gie_runtime','tests/motor_gerenciamento','tests/load_balancer','tests/integracoes','tests/observabilidade','tests/high_autonomy_v2','demo/simulation/tests']
    rows=[]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
    for suite in suites:
        r=subprocess.run([sys.executable,'-B',__file__,'--suite',suite],capture_output=True,text=True,encoding='utf-8',env=env)
        print(r.stdout);print(r.stderr,file=sys.stderr)
        try:row=json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:row={'suite':suite,'success':False}
        rows.append(row)
    out=ROOT/'outputs/publication_local';out.mkdir(parents=True,exist_ok=True)
    (out/('tests_demo.json' if a.demo else 'tests_core.json')).write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return 0 if all(x['success'] for x in rows) else 1
if __name__=='__main__':raise SystemExit(main())
