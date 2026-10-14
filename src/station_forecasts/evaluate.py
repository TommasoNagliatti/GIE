"""Held-out evaluation: requires frozen models and never updates selection."""
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .core import *
from .predict import Forecaster
from .metrics import *

def evaluate(station,version='v1'):
    model=Forecaster(station,version);c=model.c;out=REPORT/station
    if (out/'test_metrics.json').exists():raise RuntimeError('Final test already recorded; cannot overwrite')
    for file,expected in model.freeze['code_sha256'].items():
        if digest(ROOT/file)!=expected:raise ValueError('Frozen pipeline changed: '+file)
    if digest(out/'validation_metrics.json')!=model.freeze['validation_metrics_sha256']:raise ValueError('Validation changed')
    freeze_hash=digest(model.folder/'freeze.json');started=pd.Timestamp.now(tz='UTC').isoformat()
    write(out/'test_started.json',dict(started_at=started,freeze_sha256=freeze_hash,evaluator_sha256=digest(__file__),selection=model.selection))
    d=load(c,'test');positions=origins(d,c,'test');b,e,q,o,h,t=model.candidates(d,positions);y=labels(d,o,h);sel=model.selection
    bm={k:motor1(y[:,0],v,model.meta['train_peak_p90_kw']) for k,v in b.items()}
    em={k:motor2(y,v,c,sel['candidate_event_thresholds'][k]) for k,v in e.items()}
    qm={k:quantile(y[:,1],v,e[sel['motor2']][:,1]) for k,v in q.items()}
    detail=[]
    for horizon in range(1,49):
        mask=h==horizon
        detail.append(dict(horizon=horizon,motor1={k:motor1(y[mask,0],v[mask],model.meta['train_peak_p90_kw']) for k,v in b.items()},
          motor2={k:motor2(y[mask],v[mask],c,sel['candidate_event_thresholds'][k]) for k,v in e.items()},
          q90={k:quantile(y[mask,1],v[mask],e[sel['motor2']][mask,1]) for k,v in q.items()}))
    write(out/'test_horizons.json',detail)
    p=e[sel['motor2']];forecast=pd.DataFrame(dict(origin=d.index[o].map(lambda v:v.isoformat()),issue_time=(d.index[o]+pd.Timedelta(minutes=c['step_minutes'])).map(lambda v:v.isoformat()),
      timestamp_previsto=t.map(lambda v:v.isoformat()),horizon=h,building_actual=y[:,0],building_pred=b[sel['motor1']],
      power_actual=y[:,1],power_pred=p[:,1],q90_raw=q[sel['q90']],power_upper=np.maximum(p[:,1],q[sel['q90']]),
      occupied_actual=y[:,2],occupied_pred=p[:,2],arrivals_actual=y[:,3],arrivals_pred=p[:,3],queue_actual=y[:,4],queue_pred=p[:,4],queue_risk=p[:,5],event_probability=p[:,6]))
    forecast.to_csv(out/'test_predictions.csv.gz',index=False,float_format='%.7f',compression={'method':'gzip','mtime':0})
    bins=[]
    for lo,hi in zip(np.arange(0,1,.1),np.arange(.1,1.1,.1)):
        mask=(p[:,5]>=lo)&(p[:,5]<(hi if hi<1 else 1.000001))
        bins.append(dict(low=float(lo),high=float(hi),n=int(mask.sum()),predicted_mean=float(p[mask,5].mean()) if mask.any() else None,observed_rate=float(y[mask,5].mean()) if mask.any() else None))
    write(out/'queue_calibration.json',bins)
    sessions=pd.read_csv(ROOT/c['dataset_dir']/'sessions.csv',keep_default_na=False)
    arrival=dates(sessions.chegada,c['timezone']);start,end=[pd.Timestamp(v,tz=c['timezone']) for v in c['periods']['test']]
    sessions=sessions[(arrival>=start)&(arrival<end)].copy();records=[]
    for row in sessions.itertuples():
        if not row.inicio:continue
        a=pd.Timestamp(row.inicio).floor(f"{c['step_minutes']}min");z=pd.Timestamp(row.termino)
        record=dict(session_id=row.session_id,arrival=row.chegada,start=row.inicio,end=row.termino)
        for horizon in [1,4,16,48]:
            mask=(h==horizon)&(t>=a)&(t<z)&(y[:,1]>.1)
            record[f'h{horizon}_rows']=int(mask.sum())
            record[f'h{horizon}_any_detected']=bool((p[mask,6]>=sel['event_threshold']).any()) if mask.any() else None
            record[f'h{horizon}_mae_kw']=float(np.abs(p[mask,1]-y[mask,1]).mean()) if mask.any() else None
            arrival_slot=pd.Timestamp(row.chegada).floor(f"{c['step_minutes']}min")
            amask=(h==horizon)&(t==arrival_slot)
            record[f'h{horizon}_arrival_detected']=bool((p[amask,6]>=sel['event_threshold']).any()) if amask.any() else None
        records.append(record)
    pd.DataFrame(records).to_csv(out/'test_session_diagnostics.csv',index=False)
    summary=dict(station_id=station,all_data_synthetic=True,selection=sel,freeze_sha256=freeze_hash,started_at=started,finished_at=pd.Timestamp.now(tz='UTC').isoformat(),
      origins=len(positions),overlapping_origin_horizon_rows=len(y),independent_arrivals=len(sessions),connected_sessions=len(records),
      motor1=bm,motor2=em,q90=qm,notes=['Session diagnostics use aggregate site power; cannot attribute shared station load to one EV.',
      'Overlapping forecast rows are not independent EV sessions.', 'All choices and probability thresholds frozen before reading test.'])
    write(out/'test_metrics.json',summary)
    fig,ax=plt.subplots(3,2,figsize=(15,10),layout='constrained')
    for col,hor in enumerate([1,16]):
        mask=(h==hor)&(t<start+pd.Timedelta(days=7))
        ax[0,col].plot(t[mask],y[mask,0],label='Synthetic actual');ax[0,col].plot(t[mask],b[sel['motor1']][mask],label='Forecast',alpha=.8)
        ax[0,col].set(title=f'Building +{hor*15} min',ylabel='kW');ax[0,col].legend()
        ax[1,col].plot(t[mask],y[mask,1],label='Synthetic actual');ax[1,col].plot(t[mask],p[mask,1],label='Point');ax[1,col].plot(t[mask],np.maximum(p[:,1],q[sel['q90']])[mask],label='Upper',alpha=.7)
        ax[1,col].set(title=f'EV +{hor*15} min',ylabel='kW');ax[1,col].legend()
        scores=bm if col==0 else em;keys=list(scores);vals=[scores[k]['mae'] if col==0 else scores[k]['power']['mae'] for k in keys]
        ax[2,col].bar(keys,vals);ax[2,col].tick_params(axis='x',rotation=25);ax[2,col].set(title='Test MAE building' if col==0 else 'Test MAE EV (not selection alone)',ylabel='kW')
    fig.suptitle(station+' - synthetic held-out Nov/Dec 2025');fig.savefig(out/'test_diagnostics.png',dpi=130);plt.close(fig)
    fig,ax=plt.subplots(2,1,figsize=(14,7),layout='constrained')
    active=np.flatnonzero((h==1)&(y[:,1]>.1));centre=t[active[0]] if len(active) else start
    mask=(h==4)&(t>=centre-pd.Timedelta(hours=6))&(t<centre+pd.Timedelta(hours=18))
    ax[0].plot(t[mask],y[mask,1],label='Synthetic EV');ax[0].plot(t[mask],p[mask,1],label='Point +1h');ax[0].plot(t[mask],np.maximum(p[:,1],q[sel['q90']])[mask],label='Upper +1h');ax[0].legend();ax[0].set(ylabel='kW')
    ax[1].plot(t[mask],p[mask,6],label='Occurrence probability');ax[1].axhline(sel['event_threshold'],linestyle='--',label='Frozen threshold');ax[1].legend();ax[1].set(ylabel='Probability',ylim=(0,1))
    fig.suptitle(station+' - first active held-out episode');fig.savefig(out/'event_diagnostic.png',dpi=130);plt.close(fig)
    assert digest(model.folder/'freeze.json')==freeze_hash
    write(out/'test_artifacts_sha256.json',{p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='test_artifacts_sha256.json'})
    print(station,'TEST',json.dumps(dict(selection=sel,building=bm[sel['motor1']],ev=em[sel['motor2']],q90=qm[sel['q90']],sessions=len(sessions))),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--station',required=True);parser.add_argument('--version',default='v1');a=parser.parse_args();evaluate(a.station,a.version)
