from pathlib import Path
import unittest,sys,io,json,time,subprocess,re,os
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
def main():
    suite=unittest.TestSuite()
    core=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','unittest','discover','-s',str(ROOT/'tests/gie_control'),'-p','test_control.py','-v'],
                        cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1'))
    suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'tests/gie_control'),pattern='test_dashboard.py'))
    import importlib.util
    spec=importlib.util.spec_from_file_location('legacy_dashboard_tests',ROOT/'demo/high_autonomy_v2/test_dashboard.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    text=io.StringIO();start=time.perf_counter();r=unittest.TextTestRunner(stream=text,verbosity=2).run(suite)
    out=ROOT/'outputs/presentation_v1';out.mkdir(exist_ok=True,parents=True)
    core_text=core.stdout+core.stderr;count=re.search(r'Ran (\d+) tests?',core_text);core_count=int(count[1]) if count else 0
    (out/'tests.txt').write_text(core_text+'\n'+text.getvalue(),encoding='utf-8')
    (out/'tests.json').write_text(json.dumps({'tests':r.testsRun+core_count,'core_tests':core_count,'ui_tests':r.testsRun,
          'failures':len(r.failures),'errors':len(r.errors),'core_exit':core.returncode,
          'passed':r.wasSuccessful() and core.returncode==0,'elapsed_seconds':time.perf_counter()-start},indent=2))
    print(core_text+text.getvalue());sys.exit(not r.wasSuccessful() or core.returncode!=0)
if __name__=='__main__':main()
