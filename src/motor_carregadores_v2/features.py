"""Reutiliza features V1 sem modificá-las."""
from motor_carregadores.features import *
V1_MODELS=MODELS
MODELS=ROOT/'models/carregadores/v2'
OUTPUT=ROOT/'outputs/motor_carregadores/v2'
METHODS=['persistencia','semana_anterior','media_4semanas','residual_v1']
def candidates(data,h,model,base=None):
    b=power_baselines(data,h)
    return {'persistencia':b['persistencia'].to_numpy(),'semana_anterior':b['semana_anterior'].to_numpy(),
        'media_4semanas':b['media_4semanas'].to_numpy(),
        'residual_v1':np.clip(b['media_4semanas'].to_numpy()+model.predict(horizon_features(data,h,base),num_threads=2),0,88)}
def select(scores):
    if set(scores.partition)!= {'validation'}:raise ValueError('Seleção aceita apenas maio.')
    rows=[]
    for h in HORIZONS:
        sub=scores[scores.horizon==h].copy()
        if len(sub)!=4 or set(sub.method)!=set(METHODS):raise ValueError('Candidatos incompletos.')
        sub['order']=sub.method.map({m:i for i,m in enumerate(METHODS)})
        row=sub.sort_values(['mae','order']).iloc[0]
        rows.append({'horizon':h,'minutes':h*15,'method':row.method,'validation_mae':float(row.mae)})
    return rows
def verify(name):
    manifest=json.loads((OUTPUT/name).read_text(encoding='utf-8'))
    changed=[p for p,h in manifest.items() if digest(ROOT/p)!=h]
    if changed:raise RuntimeError('Arquivo preservado alterado: '+str(changed))
    return len(manifest)
