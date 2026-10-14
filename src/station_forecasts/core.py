from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'reports/station_forecasts/v1'
TARGETS=['building','power','occupancy','arrivals','queue','risk','event']
COLUMNS=['consumo_predio_kw','potencia_solicitada_kw','carregadores_ocupados','carros_chegando','carros_na_fila']
SEED=20261011
MIN_HISTORY=2689

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False,default=str),encoding='utf-8')
def config(profile):
    folder=ROOT/'data/synthetic_profiles'/profile
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    ev=m['equipment']['evse']
    return dict(station_id=m['station_id'],profile=profile,timezone=m['timezone'],location=m['location'],step_minutes=m['interval_minutes'],horizons=48,
      dataset_dir=str(folder.relative_to(ROOT)).replace('\\','/'),n_evse=len(ev),evse_kw=[e['max_kw'] for e in ev],ev_limit_kw=sum(e['max_kw'] for e in ev),queue_limit=3,
      minimum_history=MIN_HISTORY,schema='emps-forecast-v1',seed=SEED,origin='SIMULATED',
      periods={'train':['2025-01-01','2025-09-01'],'validation':['2025-09-01','2025-11-01'],'test':['2025-11-01','2026-01-01']})
def dates(values,tz):
    ix=pd.DatetimeIndex(pd.to_datetime(values,format='mixed'))
    if ix.tz is None:raise ValueError('Timezone/offset required, naive timestamps rejected')
    return ix.tz_convert(tz)

def validate(b,e,c):
    b=b.copy();e=e.copy();step=pd.Timedelta(minutes=c['step_minutes'])
    for a in [b,e]:
        a.index=dates(a.pop('timestamp'),c['timezone'])
        if len(a)==0 or not a.index.equals(pd.date_range(a.index[0],periods=len(a),freq=step)):raise ValueError('Empty, unordered, duplicate or gapped timeline')
        if not ((a.index.minute%c['step_minutes']==0)&(a.index.second==0)&(a.index.microsecond==0)).all():raise ValueError('Misaligned intervals')
        if not a.station_id.eq(c['station_id']).all():raise ValueError('Station mismatch')
        if not a.origin.eq(c['origin']).all():raise ValueError('Provenance mismatch')
        if not dates(a.available_at,c['timezone']).equals(a.index+step):raise ValueError('Invalid availability')
    if not b.index.equals(e.index):raise ValueError('Building/EV timelines differ')
    cols=COLUMNS+['potencia_entregue_kw','energia_entregue_kwh','carros_conectados','ocupacao_pct']
    d=b[['consumo_predio_kw','temperatura_externa_c','umidade_relativa_pct','weather_available_at']].join(e[[x for x in cols if x!='consumo_predio_kw']])
    num=d.drop(columns='weather_available_at')
    if not np.isfinite(num.to_numpy(float)).all():raise ValueError('Nonfinite history')
    if (num.drop(columns='temperatura_externa_c')<0).any().any():raise ValueError('Negative physical value')
    if not d.umidade_relativa_pct.between(0,100).all():raise ValueError('Humidity out of bounds')
    for key,limit in [('potencia_solicitada_kw',c['ev_limit_kw']),('potencia_entregue_kw',c['ev_limit_kw']),('carregadores_ocupados',c['n_evse']),('carros_na_fila',c['queue_limit'])]:
        if (d[key]>limit+1e-7).any():raise ValueError('Physical limit: '+key)
    for key in ['carregadores_ocupados','carros_conectados','carros_chegando','carros_na_fila']:
        if (d[key]%1!=0).any():raise ValueError('Noninteger counts')
    if not np.allclose(d.ocupacao_pct,d.carregadores_ocupados*100/c['n_evse']):raise ValueError('Occupancy inconsistent')
    if not np.array_equal(d.carros_conectados,d.carregadores_ocupados):raise ValueError('Connections inconsistent')
    if not np.allclose(d.energia_entregue_kwh,d.potencia_entregue_kw*c['step_minutes']/60,atol=1e-7):raise ValueError('Energy inconsistent')
    if not np.allclose(b.consumo_predio_kwh,d.consumo_predio_kw*c['step_minutes']/60,atol=1e-7):raise ValueError('Building energy inconsistent')
    if (d.potencia_entregue_kw>d.potencia_solicitada_kw+1e-7).any():raise ValueError('Delivery exceeds request')
    wa=dates(d.weather_available_at,c['timezone'])
    if (wa<d.index+step).any() or not wa.is_monotonic_increasing:raise ValueError('Invalid weather availability')
    d['weather_available_at']=wa
    return d

def input_files(c,partition='validation'):
    start=pd.Timestamp(c['periods']['train'][0]);end=pd.Timestamp(c['periods'][partition][1])
    months=pd.date_range(start.normalize().replace(day=1),end,freq='MS',inclusive='left')
    folder=ROOT/c['dataset_dir']/'monthly'
    return {k:[folder/f"{k}_{m:%Y-%m}.csv" for m in months] for k in ['building','ev']}

def load(c,partition='validation'):
    if c['horizons']!=48 or c['step_minutes']<=0 or 60%c['step_minutes']!=0:raise ValueError('Unsupported horizon/interval')
    if c['horizons']>1440//c['step_minutes'] or c['minimum_history']<=10080//c['step_minutes']:raise ValueError('Lag history/horizon incompatible with configured step')
    frames={k:pd.concat([pd.read_csv(p) for p in paths],ignore_index=True) for k,paths in input_files(c,partition).items()}
    return validate(frames['building'],frames['ev'],c)

def origins(d,c,partition,stride=1):
    start,end=[pd.Timestamp(x,tz=c['timezone']) for x in c['periods'][partition]]
    step=pd.Timedelta(minutes=c['step_minutes'])
    mask=(np.arange(len(d))>=c['minimum_history']-1)&(d.index>=start)&(d.index+(c['horizons']+1)*step<=end)&(np.arange(len(d))+c['horizons']<len(d))
    return np.flatnonzero(mask)[::stride]

def features(d,c,positions):
    """One row per (origin,horizon); origin-major order. No future readings."""
    positions=np.asarray(positions,dtype=int)
    if len(positions)==0 or positions.min()<c['minimum_history']-1 or positions.max()>=len(d):raise ValueError('Insufficient history')
    H=c['horizons'];step=pd.Timedelta(minutes=c['step_minutes']);h=np.tile(np.arange(1,H+1),len(positions));o=np.repeat(positions,H)
    target=d.index[o]+h*step;issue=d.index[o]+step
    x={'horizon':h,'target_slot':target.hour*60//c['step_minutes']+target.minute//c['step_minutes'],'target_dow':target.dayofweek,
       'target_month':target.month,'target_hour_sin':np.sin(2*np.pi*(target.hour+target.minute/60)/24),'target_hour_cos':np.cos(2*np.pi*(target.hour+target.minute/60)/24)}
    daily=24*60//c['step_minutes'];weekly=daily*7
    for col in COLUMNS+['potencia_entregue_kw']:
        a=d[col].to_numpy(float)
        x[col+'_now']=a[o]
        for lag in [1,4,16,daily,weekly]:x[col+f'_lag{lag}']=a[o-lag]
        for w in [4,16,daily]:x[col+f'_mean{w}']=d[col].rolling(w).mean().to_numpy()[o]
        x[col+'_previous_day_target']=a[o+h-daily]
        x[col+'_previous_week_target']=a[o+h-weekly]
    # Search by known-at time, never by future row timestamp. Repeated hourly stamps
    # choose the last sample of the COMPLETED source hour.
    widx=pd.DatetimeIndex(d.weather_available_at)
    wi=widx.searchsorted(issue,side='right')-1
    if (wi<0).any():raise ValueError('No causal weather observation')
    for col in ['temperatura_externa_c','umidade_relativa_pct']:x[col+'_known']=d[col].to_numpy()[wi]
    x['weather_age_minutes']=(issue-widx[wi]).total_seconds()/60
    frame=pd.DataFrame(x).round(6).astype('float32')
    if not np.isfinite(frame.to_numpy()).all():raise ValueError('Invalid features')
    return frame,o,h,target

def labels(d,o,h):
    y=d[COLUMNS].to_numpy()[o+h]
    return np.column_stack([y,(y[:,4]>0).astype(float),(y[:,1]>.1).astype(float)])

def bound(p,c):
    p=np.maximum(0,np.array(p,dtype=float))
    p[:,1]=np.minimum(p[:,1],c['ev_limit_kw']);p[:,2]=np.clip(p[:,2],0,c['n_evse']);p[:,4]=np.minimum(p[:,4],c['queue_limit']);p[:,5:]=np.clip(p[:,5:],0,1)
    p[:,2]=np.maximum(p[:,2],p[:,1]/max(c['evse_kw']))
    return p

def fit_frequency(d,c):
    start,end=[pd.Timestamp(x,tz=c['timezone']) for x in c['periods']['train']]
    t=d[(d.index>=start)&(d.index<end)];a=t[COLUMNS].to_numpy();y=np.column_stack([a,(a[:,4]>0),(a[:,1]>.1)])
    records={}
    for day in range(7):
        for hour in range(24):
            hourly=y[t.index.hour==hour];local=y[(t.index.dayofweek==day)&(t.index.hour==hour)]
            if len(hourly)==0:raise ValueError('Training needs every hour')
            mean=(local.sum(axis=0)+96*hourly.mean(axis=0))/(len(local)+96)
            records[f'{day}_{hour}']={'mean':mean.tolist(),'q90':float(np.quantile(hourly[:,1],.9))}
    return records

def baselines(d,c,o,h,target,freq):
    a=d[COLUMNS].to_numpy();out={}
    for name,where in [('persistence',o),('previous_day',o+h-24*60//c['step_minutes']),('previous_week',o+h-7*24*60//c['step_minutes'])]:
        v=a[where];out[name]=bound(np.column_stack([v,(v[:,4]>0),(v[:,1]>.1)]),c)
    rec=[freq[f'{dw}_{hr}'] for dw,hr in zip(target.dayofweek,target.hour)]
    out['frequency']=bound(np.array([v['mean'] for v in rec]),c);out['zero']=np.zeros((len(o),7))
    return out,np.array([v['q90'] for v in rec])
