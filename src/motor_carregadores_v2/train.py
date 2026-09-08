"""Ajusta apenas Q90; seleciona potência por horizonte exclusivamente em maio."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import lightgbm as lgb
from motor_carregadores_v2.features import *
from motor_carregadores.train import PARAMS
from motor_carregadores.metrics import regression
def train():
    if MODELS.exists():raise RuntimeError('V2 já existe; não sobrescrever.')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    folders=['src/motor_consumo','models/consumo_predio','outputs/motor_consumo','src/motor_carregadores','models/carregadores/v1','outputs/motor_carregadores/v1','data']
    files=[p for folder in folders for p in (ROOT/folder).rglob('*') if p.is_file()]+[ROOT/'requirements.txt']
    write_json(OUTPUT/'preservation_before.json',{str(p.relative_to(ROOT)):digest(p) for p in files})
    write_json(OUTPUT/'protocol.json',{'fit':'Jan-Apr','early_stopping_and_selection':'May only','june':'secondary frozen diagnostic, already inspected during V1',
        'quantile':.9,'quantile_target':'absolute requested power','upper_output':'max(point forecast, clip(raw Q90,0,88))',
        'coverage':'report raw clipped Q90 and operational upper separately; no calibration to June',
        'architecture':'V1 features and all 5 V1 models unchanged; one additional global Q90 model',
        'production_origin':'2026-06-15 07:45','rounds':250,'patience':25})
    raw=pd.read_csv(SOURCE);data=validate_frame(raw.loc[raw.timestamp<'2026-06-01'])
    print('Construindo treino e maio, sem junho...',flush=True)
    xt,yt,bt,it=make_long(data,'train');xv,yv,bv,iv=make_long(data,'validation')
    # Existing bounded-history and causal feature semantics checked before fit.
    t=pd.Timestamp('2026-05-15 07:45');past=data.loc[:t].iloc[-MIN_HISTORY:]
    fullbase=historical_features(data);pastbase=historical_features(past)
    for h in HORIZONS:
        pd.testing.assert_series_equal(horizon_features(data,h,fullbase).loc[t],horizon_features(past,h,pastbase).loc[t],check_exact=True)
    if iv.timestamp_previsto.max()>=pd.Timestamp('2026-06-01') or it.timestamp_previsto.max()>=pd.Timestamp('2026-05-01'):raise ValueError('Fronteira temporal cruzada.')
    model1=lgb.Booster(model_file=str(V1_MODELS/'power.txt'))
    pred={'persistencia':bv[:,0],'semana_anterior':bv[:,2],'media_4semanas':bv[:,3],
          'residual_v1':np.clip(bv[:,3]+model1.predict(xv,num_threads=2),0,88)}
    scores=[]
    for h in HORIZONS:
        mask=iv.horizon.eq(h).to_numpy()
        for name,p in pred.items():scores.append({'partition':'validation','horizon':h,'method':name,**regression(yv[mask,0],p[mask])})
    selection=select(pd.DataFrame(scores))
    MODELS.mkdir(parents=True)
    write_json(MODELS/'selector.json',{'partition':'validation','criterion':'MAE','tie_order':METHODS,'horizons':selection})
    pd.DataFrame(scores).to_csv(OUTPUT/'selection_validation.csv',index=False)
    print('Seletor de maio:',pd.Series([r['method'] for r in selection]).value_counts().to_dict(),flush=True)
    params={**PARAMS,'objective':'quantile','alpha':.9,'metric':'quantile'}
    print('Treinando um LightGBM Q90 global...',flush=True)
    model=lgb.train(params,lgb.Dataset(xt,label=yt[:,0]),num_boost_round=250,
        valid_sets=[lgb.Dataset(xv,label=yv[:,0])],valid_names=['may'],
        callbacks=[lgb.early_stopping(25,verbose=False),lgb.log_evaluation(50)])
    model.save_model(str(MODELS/'power_q90.txt'),num_iteration=model.best_iteration)
    point=np.empty(len(xv))
    for row in selection:
        m=iv.horizon.eq(row['horizon']).to_numpy();point[m]=pred[row['method']][m]
    q=np.clip(model.predict(xv,num_threads=2),0,88);upper=np.maximum(point,q)
    write_json(OUTPUT/'validation_quantile.json',{'raw_coverage_pct':float((yv[:,0]<=q).mean()*100),
        'operational_coverage_pct':float((yv[:,0]<=upper).mean()*100),'crossing_pct':float((q<point).mean()*100),
        'best_iteration':model.best_iteration,'no_coverage_calibration':True})
    meta={'feature_count':xv.shape[1],'features':list(xv.columns),'minimum_history':MIN_HISTORY,'alpha':.9,
        'parameters':params,'best_iteration':model.best_iteration,'quantile_sha256':digest(MODELS/'power_q90.txt'),
        'selector_sha256':digest(MODELS/'selector.json'),'v1_files':{p.name:digest(p) for p in V1_MODELS.glob('*') if p.is_file()},
        'counts':{'train_origins':len(xt)//48,'train_examples':len(xt),'validation_origins':len(xv)//48,'validation_examples':len(xv)},
        'source_sha256':digest(SOURCE),'june_used_for_fit_or_selection':False,'upper_rule':'max(point, clip(Q90,0,88))'}
    write_json(MODELS/'metadata.json',meta)
    verify('preservation_before.json')
    write_json(OUTPUT/'freeze_manifest.json',{str(p.relative_to(ROOT)):digest(p) for p in list(MODELS.glob('*'))+list(Path(__file__).parent.glob('*.py')) if p.is_file()})
    print('V2 congelada. Nenhum modelo V1 retreinado.',flush=True)
if __name__=='__main__':train()
