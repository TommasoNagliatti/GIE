"""Train/validation only. Save selection and artifact hashes BEFORE test command."""
import argparse,platform,time
import lightgbm as lgb
from .core import *
from .metrics import *
PARAMS=dict(learning_rate=.05,min_data_in_leaf=100,lambda_l2=2.,max_bin=63,seed=SEED,num_threads=2,deterministic=True,force_col_wise=True,verbosity=-1)

def fit(x,y,xv,yv,objective,leaves=15):
    if np.unique(y).size==1:return None,float(y[0])
    params=dict(PARAMS,objective=objective,num_leaves=leaves,metric='binary_logloss' if objective=='binary' else 'quantile' if objective=='quantile' else 'l2')
    if objective=='quantile':params['alpha']=.9
    model=lgb.train(params,lgb.Dataset(x,label=y),num_boost_round=180,valid_sets=[lgb.Dataset(xv,label=yv)],callbacks=[lgb.early_stopping(18,verbose=False)])
    return model,None

def train(c,version='v1'):
    folder=ROOT/'models/stations'/c['station_id']/version
    if folder.exists():raise RuntimeError('Refusing to overwrite existing experiment '+str(folder))
    report=REPORT/c['station_id'];report.mkdir(parents=True,exist_ok=True);folder.mkdir(parents=True)
    write(folder/'config.json',c)
    d=load(c,'validation') # physically excludes November/December
    tr=origins(d,c,'train',4);va=origins(d,c,'validation')
    x,o,h,t=features(d,c,tr);y=labels(d,o,h)
    xv,ov,hv,tv=features(d,c,va);yv=labels(d,ov,hv)
    freq=fit_frequency(d,c);write(folder/'frequency.json',freq)
    candidates,qfreq=baselines(d,c,ov,hv,tv,freq)
    peak=float(np.quantile(d.loc[d.index<pd.Timestamp(c['periods']['train'][1],tz=c['timezone']),'consumo_predio_kw'],.9))
    meta=dict(config=c,versions=dict(python=platform.python_version(),lightgbm=lgb.__version__,numpy=np.__version__,pandas=pd.__version__),
      feature_names=list(x.columns),parameters=PARAMS,train_origins=len(tr),validation_origins=len(va),train_examples=len(x),validation_examples=len(xv),
      train_origin_stride=4,validation_origin_stride=1,train_peak_p90_kw=peak,models={},all_data_synthetic=True,
      test_used=False,created_at=pd.Timestamp.now(tz='UTC').isoformat(),source_manifest_sha256=digest(ROOT/c['dataset_dir']/'manifest.json'),
      input_hashes={str(p.relative_to(ROOT)):digest(p) for paths in input_files(c).values() for p in paths},
      training_fingerprint=digest(REPORT/'PROTOCOL.md'))
    def model_head(key,yy,vy,obj,leaves=15):
        start=time.monotonic();m,constant=fit(x,yy,xv,vy,obj,leaves)
        if m is None:meta['models'][key]={'constant':constant};p=np.full(len(xv),constant)
        else:
            file=key+'.txt';m.save_model(str(folder/file));meta['models'][key]={'file':file,'sha256':digest(folder/file),'trees':m.current_iteration()};p=m.predict(xv,num_threads=2)
        print(c['station_id'],key,meta['models'][key],round(time.monotonic()-start,1),'s',flush=True)
        return p
    building={k:v[:,0] for k,v in candidates.items() if k in ['persistence','previous_day','previous_week']}
    for leaves in [15,31]:building[f'lightgbm_{leaves}']=np.maximum(0,model_head(f'building_{leaves}',y[:,0],yv[:,0],'regression',leaves))
    pred=np.zeros_like(yv)
    for j,name in enumerate(TARGETS[1:],1):pred[:,j]=model_head(name,y[:,j],yv[:,j],'binary' if name in ['risk','event'] else 'regression')
    candidates['lightgbm']=bound(pred,c)
    qlgb=np.clip(model_head('q90',y[:,1],yv[:,1],'quantile'),0,c['ev_limit_kw'])
    bm={name:motor1(yv[:,0],p,peak) for name,p in building.items()}
    em={name:motor2(yv,p,c,threshold_for(yv[:,6],p[:,6])) for name,p in candidates.items()}
    bestb=min(bm,key=lambda k:bm[k]['mae'])
    eligible=[name for name,m in em.items() if (m['detection']['recall'] or 0)>0]
    beste=min(eligible or list(em),key=lambda k:em[k]['selection_score'])
    qm={name:quantile(yv[:,1],q,candidates[beste][:,1]) for name,q in [('frequency',qfreq),('lightgbm',qlgb)]}
    bestq=min(qm,key=lambda k:qm[k]['pinball'])
    selection=dict(motor1=bestb,motor2=beste,q90=bestq,event_threshold=em[beste]['event_threshold'],candidate_event_thresholds={k:v['event_threshold'] for k,v in em.items()},
      detection_unresolved=not bool(eligible),selection_partition='validation',test_used=False,
      selected_at=pd.Timestamp.now(tz='UTC').isoformat(),version=version,station_id=c['station_id'])
    write(report/'validation_metrics.json',dict(motor1=bm,motor2=em,q90=qm))
    # Per-horizon candidate comparisons, not just pooled scores.
    rows=[]
    for horizon in range(1,49):
        mask=hv==horizon
        for name,p in building.items():rows.append(dict(motor=1,horizon=horizon,method=name,**regression(yv[mask,0],p[mask])))
        for name,p in candidates.items():rows.append(dict(motor=2,horizon=horizon,method=name,**regression(yv[mask,1],p[mask,1])))
    pd.DataFrame(rows).to_csv(report/'validation_horizons.csv',index=False)
    write(folder/'metadata.json',meta);write(folder/'selection.json',selection)
    freeze=dict(frozen_at=pd.Timestamp.now(tz='UTC').isoformat(),test_accessed=False,station_id=c['station_id'],
      files={p.name:digest(p) for p in folder.iterdir() if p.is_file()},
      code_sha256={str(p.relative_to(ROOT)):digest(p) for p in Path(__file__).parent.glob('*.py')},
      validation_metrics_sha256=digest(report/'validation_metrics.json'),protocol_sha256=digest(REPORT/'PROTOCOL.md'))
    write(folder/'freeze.json',freeze)
    print('FROZEN',selection,flush=True)
    return folder

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path);parser.add_argument('--profile',choices=['posto_24h_v1','residencial_v1']);parser.add_argument('--version',default='v1');args=parser.parse_args()
    train(json.loads(args.config.read_text(encoding='utf-8')) if args.config else config(args.profile),args.version)
