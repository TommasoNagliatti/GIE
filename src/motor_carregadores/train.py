"""Cinco modelos globais; treino e seleção limitados a janeiro–maio."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import platform,time
import lightgbm as lgb
from motor_carregadores.features import *
from motor_carregadores.metrics import regression,classification,choose_threshold
PARAMS={'learning_rate':.05,'num_leaves':15,'min_data_in_leaf':100,'lambda_l2':1.,
        'feature_fraction':1.,'bagging_fraction':1.,'seed':20260906,'num_threads':2,
        'deterministic':True,'force_col_wise':True,'verbosity':-1}
def train():
    if (MODELS/'metadata.json').exists() or list(MODELS.glob('*.txt')): raise RuntimeError('Modelos já existem; não sobrescrever a versão.')
    if not (OUTPUT/'protocol.json').exists(): raise RuntimeError('Execute auditoria primeiro.')
    # Even parsing numerical columns for fitting excludes June beforehand.
    raw=pd.read_csv(SOURCE,dtype={'timestamp':str})
    data=validate_frame(raw.loc[raw.timestamp<'2026-06-01'].copy())
    assert data.index.max()<pd.Timestamp('2026-06-01')
    print('Montando treino e validação em formato longo...',flush=True)
    xt,yt,bt,it=make_long(data,'train');xv,yv,bv,iv=make_long(data,'validation')
    assert it.timestamp_previsto.max()<pd.Timestamp('2026-05-01') and iv.timestamp_previsto.max()<pd.Timestamp('2026-06-01')
    MODELS.mkdir(parents=True,exist_ok=True)
    pred={};records=[];importance=[];started=time.time()
    for i,name in enumerate(['power','occupancy','arrivals','queue','risk']):
        params=dict(PARAMS)
        if name=='power':
            target_train=yt[:,0]-bt[:,3];target_val=yv[:,0]-bv[:,3]
            params.update(objective='regression',metric='l1')
        elif name=='risk':
            target_train=(yt[:,3]>0).astype(int);target_val=(yv[:,3]>0).astype(int)
            params.update(objective='binary',metric='binary_logloss')
        else:
            target_train=yt[:,i];target_val=yv[:,i];params.update(objective='poisson',metric='poisson')
        print(f'Treinando {name} ({len(xt)} exemplos, {xt.shape[1]} features)...',flush=True)
        ds=lgb.Dataset(xt,label=target_train,free_raw_data=True)
        vs=lgb.Dataset(xv,label=target_val,reference=ds,free_raw_data=True)
        model=lgb.train(params,ds,num_boost_round=250,valid_sets=[vs],valid_names=['may'],
            callbacks=[lgb.early_stopping(25,verbose=False),lgb.log_evaluation(50)])
        path=MODELS/(name+'.txt');model.save_model(str(path),num_iteration=model.best_iteration)
        p=model.predict(xv,num_threads=2)
        if name=='power':p=np.clip(bv[:,3]+p,0,88)
        elif name!='risk':p=np.clip(p,0,LIMITS[name])
        pred[name]=p
        records.append({'name':name,'file':path.name,'sha256':digest(path),'best_iteration':model.best_iteration,'params':params})
        importance.extend({'model':name,'feature':c,'gain':float(v)} for c,v in zip(xt.columns,model.feature_importance('gain')))
        print(f'{name}: concluído, {model.best_iteration} árvores.',flush=True)
        del ds,vs,model
    selected,grid=choose_threshold((yv[:,3]>0).astype(int),pred['risk'])
    config={'threshold':selected['threshold'],'criterion':'maximum May F1; lowest threshold on tie','partition':'validation','bounds':LIMITS}
    write_json(MODELS/'config.json',config)
    pd.DataFrame(grid).to_csv(OUTPUT/'threshold_validation.csv',index=False)
    rows=[]
    for i,name in enumerate(['persistencia','dia_anterior','semana_anterior','media_4semanas']): rows.append({'target':'power','method':name,**regression(yv[:,0],bv[:,i])})
    for i,name in enumerate(TARGETS): rows.append({'target':name,'method':'lightgbm',**regression(yv[:,i],pred[name])})
    pd.DataFrame(rows).to_csv(OUTPUT/'metrics_validation.csv',index=False)
    write_json(OUTPUT/'classification_validation.json',classification(yv[:,3]>0,pred['risk'],config['threshold']))
    pd.DataFrame(importance).to_csv(OUTPUT/'feature_importance.csv',index=False)
    pv=iv.copy()
    for i,name in enumerate(TARGETS):pv['actual_'+name]=yv[:,i];pv['pred_'+name]=pred[name]
    pv['probabilidade_fila']=pred['risk'];pv.to_csv(OUTPUT/'predictions_validation.csv',index=False,float_format='%.8f')
    metadata={'engine':'GIE Motor 2 V1','frozen':True,'test_used':False,'source_sha256':digest(SOURCE),
        'features':list(xt.columns),'feature_count':xt.shape[1],'minimum_history_rows':MIN_HISTORY,
        'models':records,'config_sha256':digest(MODELS/'config.json'),
        'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
        'split_counts':{'train_origins':int(partition_mask(data,'train').sum()),'train_examples':len(xt),
                        'validation_origins':int(partition_mask(data,'validation').sum()),'validation_examples':len(xv)},
        'queue_train_prevalence':float((yt[:,3]>0).mean()),'elapsed_seconds':time.time()-started,
        'versions':{'python':platform.python_version(),'lightgbm':lgb.__version__,'numpy':np.__version__,'pandas':pd.__version__},
        'semantics':'power excludes queue; occupancy and queue are interval maxima; t labels last observed interval start'}
    write_json(MODELS/'metadata.json',metadata)
    write_json(OUTPUT/'freeze_manifest.json',{str(p.relative_to(ROOT)):digest(p) for p in list(MODELS.glob('*'))+list(Path(__file__).parent.glob('*.py')) if p.is_file()})
    print(json.dumps({'frozen':True,'threshold':selected,'counts':metadata['split_counts'],'features':xt.shape[1]},indent=2),flush=True)
if __name__=='__main__':train()
