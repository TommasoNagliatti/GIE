"""Reproducible inference-only export. Never edits the source or old bundles."""
from pathlib import Path
import argparse,ast,hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]

FEATURES={
 'gie_control/scenarios.py':{'apply_event','execute_demo','validate_physics'},
 'motor_consumo/v1/features.py':{'validate_frame','calendar','historical_features','horizon_features'},
 'motor_consumo/features.py':{'residual_base','residual_features','weekly_baseline'},
 'motor_carregadores/features.py':{'digest','validate_frame','calendar','historical_features','horizon_features','power_baselines'},
 'motor_carregadores_v2/features.py':set(),
}
PACKAGES=('gie_control','gie_runtime','motor_gerenciamento','motor_gerenciamento_v2','load_balancer','integracoes')
SKIP={'demo.py','demo_revision.py','train.py','evaluate.py','run_tests.py'}

def source_text(rel):
    text=(ROOT/'src'/rel).read_text(encoding='utf-8-sig')
    if rel not in FEATURES and not rel.endswith('/predict.py'):return text
    tree=ast.parse(text);nodes=[]
    for node in tree.body:
        if rel in FEATURES and isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name not in FEATURES[rel]:continue
        if isinstance(node,ast.If) and '__name__' in ast.unparse(node.test):continue
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('PARAMS','SCENES') for t in node.targets):continue
        if isinstance(node,ast.ImportFrom) and node.module=='motor_consumo.v1.features':
            node.names=[n for n in node.names if n.name not in ('load_data','split_masks','write_json')]
        nodes.append(node)
    # Inference function bodies remain structurally identical; only offline helpers/CLI removed.
    return ast.unparse(ast.Module(body=nodes,type_ignores=[]))+'\n'

def build(destination):
    dest=Path(destination).resolve()
    if dest.exists():raise FileExistsError('Bundle exists; choose a new --output directory to preserve it')
    if dest==ROOT or ROOT.is_relative_to(dest):raise ValueError('Unsafe bundle destination')
    dest.mkdir(parents=True)
    copied={}
    def copy(rel):
        src=ROOT/rel;target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
        copied[rel]={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'bundle_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    def py(rel):
        dst=dest/'src'/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(source_text(rel),encoding='utf-8')
        copied['src/'+rel]={'source_sha256':hashlib.sha256((ROOT/'src'/rel).read_bytes()).hexdigest(),'bundle_sha256':hashlib.sha256(dst.read_bytes()).hexdigest()}
    for package in PACKAGES:
        for path in sorted((ROOT/'src'/package).rglob('*.py')):
            if '__pycache__' not in path.parts and path.name not in SKIP and not path.name.startswith('test_'):
                py(path.relative_to(ROOT/'src').as_posix())
    for package in ('motor_consumo','motor_consumo/v1','motor_carregadores','motor_carregadores_v2'):
        for name in ('__init__.py','features.py'):
            py(package+'/'+name)
        if package!='motor_consumo/v1':py(package+'/predict.py')
    m1=ROOT/'models/consumo_predio/v2'
    meta=json.loads((m1/'metadata.json').read_text())
    selection=json.loads((m1/'selector.json').read_text())['horizons']
    for name in ('metadata.json','selector.json'):copy('models/consumo_predio/v2/'+name)
    for r in selection:
        if r['method']=='residual_v2':copy('models/consumo_predio/v2/'+meta['models'][r['horizon']-1]['file'])
        elif r['method']=='lightgbm_v1':copy(f"models/consumo_predio/v1/horizon_{r['horizon']:02d}.txt")
    meta2=json.loads((ROOT/'models/carregadores/v2/metadata.json').read_text())
    for name in meta2['v1_files']:copy('models/carregadores/v1/'+name)
    for name in ('metadata.json','selector.json','power_q90.txt'):copy('models/carregadores/v2/'+name)
    copy('site_profiles/Commercial_HighAutonomy_V2.json')
    copy('src/gie_control/assets/scenes.json')
    (dest/'gie').mkdir()
    (dest/'gie/__init__.py').write_text('from pathlib import Path\nimport sys\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))\nfrom gie_control import GIEEngine,GIEControl,History,CurrentState,EVSEState\n',encoding='utf-8')
    (dest/'requirements.txt').write_text('\n'.join(line for line in (ROOT/'requirements.txt').read_text().splitlines() if line.split('==')[0] in ('numpy','pandas','lightgbm','scipy'))+'\n')
    shutil.copyfile(ROOT/'docs/INTEGRATION_TEMPLATE.md',dest/'INTEGRATION.md')
    version={'version':'presentation-integration-1.0','profile':'Commercial_HighAutonomy_V2','core_changed':False,
       'source_commit':subprocess.check_output(['git','-c','safe.directory=C:/Users/Tommaso/Desktop/Gie','-C',str(ROOT),'rev-parse','HEAD']).decode().strip(),
       'source_is_working_tree':True,'files':copied,'features_export':'AST removal of unused training/audit helpers and CLI; inference bodies unchanged'}
    (dest/'VERSION.json').write_text(json.dumps(version,indent=2),encoding='utf-8')
    return {'path':str(dest),'files':sum(p.is_file() for p in dest.rglob('*')),'bytes':sum(p.stat().st_size for p in dest.rglob('*') if p.is_file())}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist/GIE_Integration')
    print(json.dumps(build(parser.parse_args().output),indent=2))
