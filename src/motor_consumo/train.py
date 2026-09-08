"""Treina resíduos e congela seletor usando somente maio; não avalia junho."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib
import json
import platform
import time
import numpy as np
import pandas as pd
import lightgbm as lgb
from motor_consumo.features import *
from motor_consumo.v1.evaluate import metrics


def train():
    data=load_data(SOURCE)
    v1=json.loads((V1_MODELS/'metadata.json').read_text(encoding='utf-8'))
    source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash!=v1['source']['sha256']:
        raise ValueError('Fonte oficial difere da V1.')
    # Physically exclude June from feature construction, targets, fit and selection.
    data=data.loc[data.index<'2026-06-01'].copy()
    base=residual_base(data); v1base=historical_features(data)
    masks=masks_for(data,base); tr=masks['train']; va=masks['validation']
    MODELS.mkdir(parents=True,exist_ok=True); OUTPUT.mkdir(parents=True,exist_ok=True)
    scores=[]; model_records=[]; predictions=[]; gains=[]
    start=time.perf_counter()
    for h in HORIZONS:
        x=residual_features(data,h,base)
        target=residual_target(data,h)
        if x.loc[tr|va].isna().any().any() or target.loc[tr|va].isna().any():
            raise ValueError('Features/targets incompletos.')
        ds=lgb.Dataset(x.loc[tr],label=target.loc[tr])
        valid=lgb.Dataset(x.loc[va],label=target.loc[va],reference=ds)
        model=lgb.train(PARAMS,ds,num_boost_round=400,valid_sets=[valid],valid_names=['may'],
                        callbacks=[lgb.early_stopping(35,verbose=False)])
        path=MODELS/f'residual_{h:02d}.txt'
        model.save_model(str(path),num_iteration=model.best_iteration)
        model_records.append({'horizon':h,'file':path.name,'best_iteration':model.best_iteration,
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        weekly=weekly_baseline(data,h).loc[va].to_numpy()
        # Residual may be negative. Floor ONLY the reconstructed total consumption.
        residual_pred=model.predict(x.loc[va],num_threads=2)
        v1model=lgb.Booster(model_file=str(V1_MODELS/f'horizon_{h:02d}.txt'))
        actual=data.consumo_predio_kw.shift(-h).loc[va].to_numpy()
        candidates={'persistencia':data.consumo_predio_kw.loc[va].to_numpy(),
                    'semana_anterior':weekly,
                    'lightgbm_v1':np.maximum(0,v1model.predict(horizon_features(data,h,v1base).loc[va],num_threads=2)),
                    'residual_v2':np.maximum(0,weekly+residual_pred)}
        for method,p in candidates.items():
            scores.append({'partition':'validation','method':method,'horizon':h,'minutes':h*15,**metrics(actual,p)})
        predictions.append(pd.DataFrame({'timestamp_origem':data.index[va],
            'timestamp_previsto':data.index[va]+h*STEP,'horizon':h,'real_kw':actual,**candidates}))
        for name,gain in zip(x.columns,model.feature_importance(importance_type='gain')):
            gains.append({'horizon':h,'feature':name,'gain':float(gain)})
        print(f'Residual {h:02d}/48: {model.best_iteration} árvores; MAE maio={metrics(actual,candidates["residual_v2"])["mae_kw"]:.3f}',flush=True)
    score=pd.DataFrame(scores)
    selection=select_methods(score)
    selector={'selection_partition':'validation','period':'2026-05-01 / 2026-05-31',
              'criterion':'MAE kW, after reconstructing total prediction',
              'tie_order':METHODS,'june_used':False,'horizons':selection}
    write_json(MODELS/'selector.json',selector)  # Frozen BEFORE any June evaluation.
    pd.DataFrame(selection).to_csv(OUTPUT/'selection_by_horizon.csv',index=False)
    score.to_csv(OUTPUT/'validation_candidates.csv',index=False)
    pd.concat(predictions).to_csv(OUTPUT/'predictions_validation.csv',index=False,float_format='%.9f')
    pd.DataFrame(gains).to_csv(OUTPUT/'feature_importance.csv',index=False)
    meta={'engine':'Goodwe Motor 1 V2 híbrido','feature_names':list(x.columns),'feature_count':len(x.columns),
          'source_path':str(SOURCE),'source_sha256':source_hash,'minimum_history_rows':MIN_HISTORY,
          'parameters':PARAMS,'max_rounds':400,'early_stopping_rounds':35,'residual_target':'y(t+h)-y(t+h-672)',
          'reconstruction':'max(0, weekly_baseline + signed_residual_prediction)',
          'train_origins':int(tr.sum()),'validation_origins':int(va.sum()),
          'fit_period':'Jan-Apr 2026','early_stopping_and_selection':'May 2026',
          'june_role':'secondary diagnostic, previously inspected; NOT independent final test',
          'independent_final_test':'pending new completely unobserved period',
          'selection_caveat':'May reused for early stopping and method selection; optimistic selection estimate',
          'models':model_records,'v1_models':str(V1_MODELS),
          'v1_model_hashes':{r['file']:r['sha256'] for r in v1['models']},
          'selector_sha256':hashlib.sha256((MODELS/'selector.json').read_bytes()).hexdigest(),
          'timestamp_semantics':'t is START of last observed interval, available at t+15min; next interval begins at issuance',
          'seed':PARAMS['seed'],'versions':{'python':platform.python_version(),'lightgbm':lgb.__version__,'numpy':np.__version__,'pandas':pd.__version__},
          'elapsed_seconds':time.perf_counter()-start}
    write_json(MODELS/'metadata.json',meta)
    print('Seletor congelado. Contagens:',pd.DataFrame(selection).method.value_counts().to_dict(),flush=True)


if __name__=='__main__': train()
