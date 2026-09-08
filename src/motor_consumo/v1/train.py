"""Treina 48 horizontes diretos, selecionando iterações somente em maio."""
if __package__ in (None,''):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import argparse
import hashlib
import platform
import time
import numpy as np
import pandas as pd
import lightgbm as lgb
from motor_consumo.v1.features import (SOURCE,MODELS,OUTPUT,STEP,HORIZONS,audit_source,
    historical_features,horizon_features,targets,target_name,split_masks,write_json)

PARAMS={'objective':'regression','metric':'l1','learning_rate':0.05,'num_leaves':15,
        'min_data_in_leaf':40,'lambda_l2':1.0,'feature_fraction':1.0,'bagging_fraction':1.0,
        'seed':20260905,'num_threads':2,'deterministic':True,'force_col_wise':True,'verbosity':-1}


def train(source=SOURCE):
    data,audit=audit_source(source)
    base=historical_features(data)
    masks=split_masks(data,base)
    y=targets(data)
    # Baselines are established before fitting, on validation only.
    from motor_consumo.v1.evaluate import baseline_metrics
    baseline=baseline_metrics(data,'validation')
    baseline.to_csv(OUTPUT/'baselines_validation_before_training.csv',index=False)
    print('Baselines de maio calculados. Iniciando treino; junho não será usado para seleção.',flush=True)
    MODELS.mkdir(parents=True,exist_ok=True)
    split_info={}
    manifest=pd.DataFrame(index=data.index)
    manifest['partition']='excluded'
    for name,mask in masks.items():
        ix=data.index[mask]
        split_info[name]={'origins':len(ix),'first_origin':str(ix[0]),'last_origin':str(ix[-1]),
                          'last_target':str(ix[-1]+48*STEP),'target_pairs':len(ix)*48}
        manifest.loc[mask,'partition']=name
    manifest.to_csv(OUTPUT/'split_manifest.csv',index_label='timestamp_origem')
    y.to_csv(OUTPUT/'targets_48.csv',index_label='timestamp_origem',float_format='%.6f')
    model_records=[]
    imports=[]
    start=time.perf_counter()
    for h in HORIZONS:
        x=horizon_features(data,h,base)
        train_mask=masks['train']; val_mask=masks['validation']
        assert not x.loc[train_mask].isna().any().any()
        assert y.loc[train_mask,target_name(h)].notna().all()
        ds=lgb.Dataset(x.loc[train_mask],label=y.loc[train_mask,target_name(h)])
        val=lgb.Dataset(x.loc[val_mask],label=y.loc[val_mask,target_name(h)],reference=ds)
        model=lgb.train(PARAMS,ds,num_boost_round=400,valid_sets=[val],valid_names=['may'],
                        callbacks=[lgb.early_stopping(35,verbose=False)])
        path=MODELS/f'horizon_{h:02d}.txt'
        model.save_model(str(path),num_iteration=model.best_iteration)
        model_records.append({'horizon':h,'minutes':h*15,'target':target_name(h),
                              'file':path.name,'best_iteration':model.best_iteration,
                              'validation_mae_kw':model.best_score['may']['l1'],
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        for name,gain in zip(x.columns,model.feature_importance(importance_type='gain')):
            imports.append({'horizon':h,'feature':name,'gain':float(gain)})
        print(f'Horizonte {h:02d}/48 (+{h*15}min): {model.best_iteration} árvores, MAE maio={model.best_score["may"]["l1"]:.3f} kW',flush=True)
    pd.DataFrame(imports).to_csv(OUTPUT/'feature_importance.csv',index=False)
    metadata={'engine':'Goodwe Motor 1','strategy':'48 direct independent LightGBM models',
              'source':audit,'splits':split_info,'feature_names':list(x.columns),'feature_count':len(x.columns),
              'minimum_history_rows':673,'horizon_count':48,'step_minutes':15,
              'target_unit':'kW average over interval','timezone':'UTC-03:00',
              'origin_semantics':'last observed interval START t; available at t+15min',
              'prediction_semantics':'target starts t+h*15min; first target begins at issuance t+15min',
              'known_future_features':'calendar only; no future weather or consumption',
              'parameters':PARAMS,'max_rounds':400,'early_stopping_rounds':35,
              'fit_period':'Jan-Apr','early_stopping_period':'May','held_out_period':'June',
              'postprocessing':'negative predictions floored to zero, shared in evaluation/inference',
              'versions':{'python':platform.python_version(),'lightgbm':lgb.__version__,'numpy':np.__version__,'pandas':pd.__version__},
              'models':model_records,'training_seconds':time.perf_counter()-start}
    write_json(MODELS/'metadata.json',metadata)
    write_json(MODELS/'feature_schema.json',{'features':list(x.columns),'targets':[target_name(h) for h in HORIZONS]})
    assert hashlib.sha256(source.read_bytes()).hexdigest()==audit['sha256']
    print(f'Treino concluído: {len(model_records)} modelos. {metadata["training_seconds"]:.1f}s',flush=True)


if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=SOURCE)
    args=parser.parse_args()
    train(args.data)
