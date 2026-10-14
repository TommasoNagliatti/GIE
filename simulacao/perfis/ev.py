"""Minute discrete-event EV simulator; AC-meter energy separate from battery SOC."""
from collections import deque
import numpy as np
import pandas as pd
from loads import INDEX, PROFILES, TZ

def simulate(profile):
    c=PROFILES[profile];rng=np.random.default_rng(c['seed']+10)
    n=c['n_evse'];size=len(INDEX)*15;events=[]
    days=pd.date_range('2025-01-01',periods=365,freq='D',tz=TZ)
    if n==1:
        for month in range(1,13):
            available=[i for i,d in enumerate(days) if d.month==month]
            for day in sorted(rng.choice(available,size=3+int(month%2==0),replace=False)):
                events.append((int(day)*1440+int(rng.integers(1020,1260)),int(rng.integers(420,600)),float(rng.uniform(10,25))))
    else:
        for d,date in enumerate(days):
            count=rng.poisson(6*(1.2 if date.dayofweek in [4,5] else .85 if date.dayofweek==6 else 1.))
            for _ in range(count):
                period=rng.choice(4,p=[.10,.25,.40,.25])
                a,b=[(0,360),(360,660),(660,1080),(1080,1440)][period]
                events.append((d*1440+int(rng.integers(a,b)),int(rng.integers(60,241)),float(rng.uniform(8,40))))
    events.sort(); sessions=[]
    for j,(arrival,dwell,energy) in enumerate(events):
        capacity=float(rng.choice([40,50,60,75,90]));soc=float(rng.uniform(.12,.55))
        energy=min(energy,(.95-soc)*capacity/.92)
        sessions.append(dict(session_id=f"{c['station_id']}_S{j+1:05d}",station_id=c['station_id'],
          arrival_minute=arrival,departure_minute=min(arrival+dwell,size),start_minute=-1,end_minute=-1,
          evse_id='',capacity_kwh=capacity,soc_initial=soc,soc_target=soc+energy*.92/capacity,
          requested_ac_kwh=energy,delivered_ac_kwh=0.,vehicle_max_kw=float(rng.choice([7.,11.,22.])) if n==2 else 7.,
          wait_minutes=0,reason='',outage_minutes=0,last_charge_minute=-1,origin='SIMULATED'))
    available=np.ones((size,n),dtype=np.uint8);faults=[]
    for evse in range(n):
        for quarter in range(4):
            start=int(rng.integers(quarter*90*1440,(quarter+1)*90*1440));duration=int(rng.integers(60,181))
            if n==1 and quarter==0:start=sessions[4]['arrival_minute']+60;duration=120
            available[start:start+duration,evse]=0
            faults.append(dict(evse_id=f'EVSE_{evse+1:02d}',start_minute=start,end_minute=start+duration,reason='simulated_maintenance'))
    req=np.zeros((size,n));power=np.zeros((size,n));occ=np.zeros((size,n),dtype=np.uint8)
    arrivals=np.zeros(size,dtype=np.int16);qcount=np.zeros(size,dtype=np.int16)
    active=[None]*n;queue=deque();cursor=0
    for t in range(size):
        for i,s in enumerate(active):
            if s is not None and t>=s['departure_minute']:
                s['end_minute']=t;s['reason']='target_reached' if s['delivered_ac_kwh']>=s['requested_ac_kwh']-1e-8 else 'departure_before_target';active[i]=None
        while cursor<len(sessions) and sessions[cursor]['arrival_minute']==t:
            s=sessions[cursor];arrivals[t]+=1;cursor+=1
            if len(queue)>=3+sum(a is None and available[t,i] for i,a in enumerate(active)):
                s['end_minute']=t;s['reason']='queue_full'
            else:queue.append(s)
        for s in list(queue):
            if t-s['arrival_minute']>45 or t>=s['departure_minute']:
                s['end_minute']=t;s['wait_minutes']=t-s['arrival_minute'];s['reason']='wait_timeout';queue.remove(s)
        for i in range(n):
            if active[i] is None and available[t,i] and queue:
                s=queue.popleft();s['start_minute']=t;s['evse_id']=f'EVSE_{i+1:02d}';s['wait_minutes']=t-s['arrival_minute'];active[i]=s
            s=active[i]
            if s is None:continue
            occ[t,i]=1
            remaining=max(0.,s['requested_ac_kwh']-s['delivered_ac_kwh'])
            soc=s['soc_initial']+s['delivered_ac_kwh']*.92/s['capacity_kwh']
            taper=1. if soc<=.8 else max(.3,1-(soc-.8)*4)
            request=min(c['evse_kw'],s['vehicle_max_kw']*taper,remaining*60)
            req[t,i]=request;power[t,i]=request*available[t,i]
            s['delivered_ac_kwh']+=power[t,i]/60
            if power[t,i]>0:s['last_charge_minute']=t+1
            if not available[t,i]:s['outage_minutes']+=1
        qcount[t]=len(queue)
    for s in sessions:
        if s['end_minute']<0:
            s['end_minute']=size;s['reason']='year_boundary';s['wait_minutes']=(size-s['arrival_minute']) if s['start_minute']<0 else s['wait_minutes']
        s['soc_final']=s['soc_initial']+s['delivered_ac_kwh']*.92/s['capacity_kwh']
        s['unmet_ac_kwh']=max(0.,s['requested_ac_kwh']-s['delivered_ac_kwh'])
        for label,key in [('chegada','arrival_minute'),('inicio','start_minute'),('termino','end_minute'),('fim_carga','last_charge_minute')]:
            s[label]=(INDEX[0]+pd.Timedelta(minutes=s[key])).isoformat() if s[key]>=0 else ''
    mean=lambda a:a.reshape(-1,15).mean(axis=1)
    maximum=lambda a:a.reshape(-1,15).max(axis=1)
    ev=pd.DataFrame(index=INDEX)
    ev['potencia_solicitada_kw']=mean(req.sum(axis=1));ev['potencia_entregue_kw']=mean(power.sum(axis=1))
    ev['carregadores_ocupados']=maximum(occ.sum(axis=1));ev['carros_conectados']=ev['carregadores_ocupados']
    ev['carros_chegando']=arrivals.reshape(-1,15).sum(axis=1);ev['carros_na_fila']=maximum(qcount)
    ev['ocupacao_pct']=ev['carregadores_ocupados']*100/n;ev['ocupacao_media_pct']=mean(occ.sum(axis=1))*100/n
    ev['fila_media']=mean(qcount);ev['energia_entregue_kwh']=ev['potencia_entregue_kw']*.25
    for i in range(n):
        ev[f'evse_{i+1:02d}_kw']=mean(power[:,i]);ev[f'evse_{i+1:02d}_available_fraction']=mean(available[:,i]);ev[f'evse_{i+1:02d}_occupied_fraction']=mean(occ[:,i])
    return ev,pd.DataFrame(sessions),pd.DataFrame(faults)
