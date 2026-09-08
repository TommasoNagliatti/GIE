"""Read-only inference regression against the pre-migration reference; no training."""
import sys,json,hashlib,importlib,ast
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
import pandas as pd
from motor_consumo.predict import MotorHibrido
from motor_consumo.v1.predict import MotorConsumo
from motor_consumo import features
assert features.ROOT==ROOT
assert features.SOURCE==ROOT/'data/consumo_predio_6_meses.csv'
assert features.MODELS==ROOT/'models/consumo_predio/v2'
assert features.V1_MODELS==ROOT/'models/consumo_predio/v1'
for package in ['motor_consumo','motor_consumo.v1']:
    for module in ['features','train','evaluate','predict']: importlib.import_module(package+'.'+module)
for p in (ROOT/'src').rglob('*.py'): ast.parse(p.read_text(encoding='utf-8'))
data=pd.read_csv(ROOT/'outputs/motor_consumo/julho_2026/consumo_predio_janeiro_julho_2026.csv')
reference=json.loads((ROOT/'docs/migracao/reference_predictions.json').read_text())
engines={'v1':MotorConsumo(),'v2':MotorHibrido()}
out=ROOT/'outputs/motor_consumo/migracao';out.mkdir(exist_ok=True)
checks=[]
for row in reference:
    result=engines[row['version']].predict(data,row['origin'])
    assert len(result)==48 and result.timestamp_previsto.astype(str).tolist()==row['timestamps']
    np.testing.assert_array_equal(result.consumo_previsto_kw.to_numpy(),np.array(row['values']))
    checks.append({'version':row['version'],'origin':row['origin'],'steps':48,'max_absolute_difference_kw':0.0})
    if row['version']=='v2' and row['origin']=='2026-06-15 07:45': result.to_csv(out/'previsao_48.csv',index=False,float_format='%.9f')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((ROOT/'docs/migracao/copy_manifest.json').read_text())
immutable=[r for r in manifest if not Path(r['destination']).is_relative_to(ROOT/'src') and not Path(r['destination']).is_relative_to(ROOT/'tests')]
for r in immutable: assert sha(Path(r['destination']))==r['sha256'],r['destination']
assert len(list((ROOT/'models/consumo_predio/v2').glob('residual_*.txt')))==48
assert len(list((ROOT/'models/consumo_predio/v1').glob('horizon_*.txt')))==48
report={'passed':True,'python':sys.executable,'no_retraining':True,'imports_ok':True,
        'immutable_copies_checked':len(immutable),'models_v1':48,'models_v2':48,
        'forecast_values_compared':480,'max_absolute_difference_kw':0.0,'checks':checks}
(out/'validacao.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
