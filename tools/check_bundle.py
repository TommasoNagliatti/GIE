"""Validate isolated bundle and identical frozen inference; no training or network."""
from pathlib import Path
import sys,json,subprocess,os,hashlib,ast
ROOT=Path(__file__).resolve().parents[1]

def probe(base,bundle=False):
    program='''import sys,json,socket
from pathlib import Path
import pandas as pd
socket.create_connection=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('Network forbidden during validation'))
if sys.argv[1]=='bundle':
 from gie import GIEEngine,GIEControl
else:
 sys.path.insert(0,str(Path.cwd()/'src'))
 from gie_control import GIEEngine,GIEControl
from gie_runtime import History,CurrentState
from gie_control.scenarios import LocalSolar
from integracoes.weather.models import horizon
from load_balancer import EVSEState
engine=GIEEngine().initialize_models()
source=Path(sys.argv[2]);t=pd.Timestamp('2026-06-15 12:00')
b=pd.read_csv(source/'consumo_predio_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
e=pd.read_csv(source/'demanda_carregadores_6_meses.csv',parse_dates=['timestamp']).set_index('timestamp')
history=History(b.loc[:t-pd.Timedelta(minutes=15)].tail(3000),e.loc[:t-pd.Timedelta(minutes=15)].tail(3000))
a=engine.components.motor1.predict(history.building,t-pd.Timedelta(minutes=15))
ev=engine.components.motor2.predict(history.ev,t-pd.Timedelta(minutes=15))
engine.components.solar=LocalSolar(pd.DataFrame({'solar_previsto_kw':300.},index=horizon(t)))
state=CurrentState(t,float(b.loc[t,'consumo_predio_kw']),44.,300.,60.,[EVSEState(f'EVSE{i}',True) for i in range(1,5)])
r=engine.run_cycle(t,history,state)
assert r['execution_allowed'],r['health']
c=GIEControl(engine=engine);c.set_mode('PRESENTATION');c.set_scene('08')
assert c.get_state()['visual_state']['grid_exporting']
print(json.dumps({'m1':a.to_dict('records'),'m2':ev.to_dict('records'),'numeric_state':r['numeric_state'],
 'model_paths':[str(engine.components.motor1.folder),str(engine.components.motor2.v1.folder)],
 'normal_steps':len(r['forecasts']['records']),'scene_export':c.get_state()['numeric_state']['grid_export_kw']},default=str,allow_nan=False))
'''
    result=subprocess.run([sys.executable,'-B','-c',program,'bundle' if bundle else 'source',str(ROOT/'data')],cwd=base,
           text=True,encoding='utf-8',capture_output=True,env=dict(os.environ,PYTHONPATH='',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1'),timeout=180)
    if result.returncode:raise RuntimeError(result.stderr[-6000:])
    return json.loads(result.stdout)

def main():
    dest=ROOT/'dist/GIE_Integration'
    files=[p for p in dest.rglob('*') if p.is_file()]
    bad=[str(p.relative_to(dest)) for p in files if any(part in ('data','demo','outputs','tests','__pycache__','.git','.venv','.venv-demo') for part in p.relative_to(dest).parts)
         or p.name in ('train.py','evaluate.py') or p.suffix in ('.csv','.png','.epw','.idf','.pyc')]
    if bad:raise AssertionError(bad)
    source=probe(ROOT);export=probe(dest,True)
    checks={'no_forbidden_files':not bad,'m1_identical':source['m1']==export['m1'],'m2_identical':source['m2']==export['m2'],
       'full_numeric_cycle_identical':source['numeric_state']==export['numeric_state'],'48_steps':export['normal_steps']==48,
       'offline_presentation':export['scene_export']>0,'models_loaded_from_bundle':all(str(dest).lower() in p.lower() for p in export['model_paths'])}
    version=json.loads((dest/'VERSION.json').read_text())
    checks['model_hashes_identical']=all(v['source_sha256']==v['bundle_sha256'] for k,v in version['files'].items() if k.startswith('models/'))
    # Verify exported inference functions preserve their original AST exactly.
    from build_integration_bundle import FEATURES
    identical=True
    for rel,names in FEATURES.items():
        trees=[ast.parse((p/'src'/rel).read_text(encoding='utf-8-sig')) for p in (ROOT,dest)]
        defs=[{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names} for tree in trees]
        identical &= defs[0]==defs[1]
    checks['inference_function_AST_identical']=identical
    report={'checks':checks,'tests':len(checks),'passed':all(checks.values()),'bytes':sum(p.stat().st_size for p in files),'files':len(files)}
    (ROOT/'outputs/presentation_v1/bundle_validation.json').write_text(json.dumps(report,indent=2))
    (ROOT/'outputs/presentation_v1/normal_cycle_numeric.json').write_text(json.dumps(export['numeric_state'],indent=2))
    print(json.dumps(report,indent=2));assert report['passed']
if __name__=='__main__':main()
