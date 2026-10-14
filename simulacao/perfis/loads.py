"""Independent appliance/event schedules. No use of original commercial curves."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
YEAR = 2025
TZ = 'America/Sao_Paulo'
INDEX = pd.date_range(f'{YEAR}-01-01', f'{YEAR+1}-01-01', freq='15min', inclusive='left', tz=TZ)
PROFILES = {
 'posto_24h_v1': dict(station_id='DEMO_POSTO_24H_001', seed=240101, n_evse=2, evse_kw=22., pv_kwp=50., inverter_kw=60., area=150., expected_range=[6000,13000]),
 'residencial_v1': dict(station_id='DEMO_CASA_001', seed=240202, n_evse=1, evse_kw=7., pv_kwp=5.5, inverter_kw=6., area=80., expected_range=[180,450]),
}
# name: rated kW, fraction of electric heat rejected outside modeled room, reference daily kWh
LOADS = {
 'residencial_v1': {'fridge':(.14,0,1.512),'standby':(.035,0,.84),'lights':(.22,0,1.1),'tv':(.18,0,.18*(4*5+5*2)/7),'fan':(.075,0,.2625),'washer':(.45,.5,.45*55/60*3/7),'kitchen':(1.2,.3,.54),'shower':(5.5,.98,2.2),'appliances':(.35,.2,.35)},
 'posto_24h_v1': {'refrigeration':(5.,.8,84.),'lights_inside':(1.2,0,28.8),'lights_outside':(2.6,1,31.2),'pos':(.6,0,14.4),'fuel_pumps':(4.4,1,36.96),'kitchen':(2.4,.7,19.2),'compressor':(1.5,1,1.6)}
}

def weather():
    epw=next((ROOT/'weather').glob('*.epw'))
    a=pd.read_csv(epw,skiprows=8,header=None)
    assert len(a)==8760 and not ((a[1]==2)&(a[2]==29)).any()
    assert np.isfinite(a[[6,8,13]].to_numpy(float)).all()
    assert a[6].between(-20,50).all() and a[8].between(0,100).all() and a[13].between(0,1400).all()
    return epw, np.repeat(a[6].to_numpy(float),60),np.repeat(a[13].to_numpy(float),60)

def schedules(profile):
    cfg=PROFILES[profile]; rng=np.random.default_rng(cfg['seed'])
    _,temp,ghi=weather(); size=len(INDEX)*15; t=np.arange(size); minute=t%1440
    days=pd.date_range('2025-01-01',periods=365,freq='D')
    loads={k:np.zeros(size) for k in LOADS[profile]}
    hvac=np.zeros(size); people=np.zeros(size)
    def event(name,start,duration,power):
        start=max(0,int(start)); end=min(size,start+int(duration))
        loads[name][start:end]=np.maximum(loads[name][start:end],power)
    if cfg['n_evse']==1:
        duty=np.clip(.45+.012*(temp-23),.35,.55)
        loads['fridge']=.14*((t+11)%40 < np.rint(40*duty))
        loads['standby'][:]=.035
        for d,date in enumerate(days):
            b=d*1440; weekend=date.dayofweek>=5; shift=int(rng.integers(-20,21))
            event('lights',b+360+shift,60,.22);event('lights',b+1080+shift,240,.22)
            event('tv',b+1110+shift,300 if weekend else 240,.18)
            event('appliances',b+int(rng.integers(600,1100)),60,.35)
            for m in [420,750,1140]: event('kitchen',b+m+shift,9,1.2)
            for m in [390,420,1170]: event('shower',b+m+shift,int(rng.integers(7,10)),5.5)
            if date.dayofweek in [1,3,5]:event('washer',b+int(rng.integers(540,900)),55,.45)
            sl=slice(b,b+1440)
            local=np.arange(1440)
            loads['fan'][sl]=.075*((temp[sl]>24)&(local>=1020)&(local<1440))
            # Bedroom AC is optional on warm evenings, with independent household choice.
            hvac[sl]=((local>=1260)&(temp[sl]>24)&(rng.random()<.65)).astype(float)
            people[sl]=np.where((local<420)|(local>=1080)|weekend,1.,.33)
    else:
        duty=np.clip(.70+.012*(temp-23),.60,.85)
        for j in range(10): loads['refrigeration']+=.5*((t+7*j)%43<np.rint(duty*43))
        loads['lights_inside'][:]=1.2;loads['lights_outside']=2.6*(ghi<20)
        loads['pos'][:]=.6
        for d,date in enumerate(days):
            b=d*1440;sl=slice(b,b+1440); local=np.arange(1440)
            busy=1.12 if date.dayofweek in [4,5] else (.9 if date.dayofweek==6 else 1.)
            # Four pumps: renewal events; no simultaneous multiplication of all ratings.
            for pump in range(4):
                k=int(rng.integers(0,20))
                while k<1440:
                    day=360<=k<1380
                    off=max(1,int(round(rng.exponential((3.67 if day else 27.)/busy))))
                    k+=off
                    loads['fuel_pumps'][b+k:min(b+k+3,b+1440)]+=1.1
                    k+=3
            shift=int(rng.integers(-15,16))
            # 16 opening hours, thermostat 50% duty, daily phase varies.
            loads['kitchen'][sl]=2.4*((local>=360)&(local<1320)&((local+shift)%30<15))
            loads['compressor'][sl]=1.5*((local>=360)&(local<1320)&((local+shift)%45<3))
            hvac[sl]=((local>=360)&(local<1380)).astype(float)
            people[sl]=np.where((local>=420)&(local<1320),.75*busy,.25)
    out=pd.DataFrame({k:v.reshape(-1,15).mean(axis=1) for k,v in loads.items()},index=INDEX)
    # Internal HVAC and people schedules are dimensionless fractions.
    out['hvac_available']=hvac.reshape(-1,15).mean(axis=1)
    out['people_fraction']=people.reshape(-1,15).mean(axis=1)
    assert all(out[k].between(0,v[0]+1e-10).all() for k,v in LOADS[profile].items())
    return out

def prepare(profile):
    d=ROOT/profile;d.mkdir(exist_ok=True)
    cfg=dict(PROFILES[profile],profile=profile,loads={k:dict(kw=v[0],lost=v[1],expected_daily_kwh=v[2]) for k,v in LOADS[profile].items()})
    (d/'parameters.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    pd.DataFrame([dict(load=k,rated_kw=v[0],expected_daily_kwh=v[2],expected_30days_kwh=v[2]*30) for k,v in LOADS[profile].items()]).to_csv(d/'load_table.csv',index=False)
    out=schedules(profile)
    # EPlus Schedule:File values are fractions of each device design level.
    eplus=out.copy()
    for k,v in LOADS[profile].items():eplus[k]/=v[0]
    eplus.to_csv(d/'schedules.csv',index=False,float_format='%.10f')
    out[list(LOADS[profile])].to_csv(d/'scheduled_loads_kw.csv',index_label='timestamp',float_format='%.10f')
    return d

if __name__=='__main__':
    for profile in PROFILES:print(prepare(profile))
