"""Generate audited annual + monthly SIMULATED datasets from the new EPlus runs."""
from pathlib import Path
import hashlib,json,platform,re,shutil,subprocess,sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from loads import ROOT,INDEX,PROFILES,LOADS,weather
from ev import simulate
REPO=ROOT.parents[1]
DATA=REPO/'data/synthetic_profiles'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save_json(p,obj):Path(p).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def write_series(frame,path,station):
    a=frame.copy();a.insert(0,'station_id',station);a.insert(1,'origin','SIMULATED')
    a.insert(2,'available_at',(a.index+pd.Timedelta(minutes=15)).map(lambda v:v.isoformat()))
    a.index=a.index.map(lambda t:t.isoformat())
    a.to_csv(path,index_label='timestamp',float_format='%.10f')

def parse_eplus_times(values):
    result=[]
    for v in values:
        mo,day,h,mi,se=map(int,re.findall(r'\d+',v))
        result.append(pd.Timestamp(2025,mo,day,tz='America/Sao_Paulo')+pd.Timedelta(hours=h,minutes=mi,seconds=se)-pd.Timedelta(minutes=15))
    return pd.DatetimeIndex(result)

def building(profile):
    directory=ROOT/profile/'run'
    meters=pd.read_csv(directory/'eplusmtr.csv');state=pd.read_csv(directory/'eplusout.csv')
    assert parse_eplus_times(meters['Date/Time']).equals(INDEX)
    assert parse_eplus_times(state['Date/Time']).equals(INDEX)
    get=lambda name:meters[next(c for c in meters if c.startswith(name+' '))].to_numpy()/3.6e6
    b=pd.DataFrame(index=INDEX)
    b['consumo_predio_kwh']=get('Electricity:Facility');b['consumo_predio_kw']=b['consumo_predio_kwh']*4
    for name,key in [('Cooling:Electricity','cooling'),('Fans:Electricity','hvac_fan'),('Heating:Electricity','heating'),('InteriorEquipment:Electricity','scheduled')]:b[key+'_kwh']=get(name)
    b['temperatura_externa_c']=state[next(c for c in state if 'Drybulb' in c)].to_numpy()
    b['umidade_relativa_pct']=state[next(c for c in state if 'Relative Humidity' in c)].to_numpy()
    b['weather_available_at']=(INDEX.floor('h')+pd.Timedelta(hours=1)).map(lambda t:t.isoformat())
    for c in state:
        if 'Zone Mean' in c:b[c.split(':')[0].lower().replace(' ','_')+'_temperature_c']=state[c].to_numpy()
    loads=pd.read_csv(ROOT/profile/'scheduled_loads_kw.csv',index_col=0)
    np.testing.assert_allclose(b['scheduled_kwh'],loads.sum(axis=1).to_numpy()*.25,atol=1e-8)
    np.testing.assert_allclose(b['consumo_predio_kwh'],b[['cooling_kwh','hvac_fan_kwh','heating_kwh','scheduled_kwh']].sum(axis=1),atol=1e-8)
    return b,loads.set_axis(INDEX)

def equipment(profile):
    c=PROFILES[profile];house=c['n_evse']==1
    template=dict(model='LX U5.4-20',nominal_kwh=5.4,usable_catalog_kwh=5.4,min_voltage_v=47.5,max_current_a=50.,charge_kw=2.2,discharge_kw=2.2,soc_initial=.5,soc_min=.2,soc_max=.95,eta_charge=.95,eta_discharge=.95)
    bat=[dict(id=f'BAT_{i:02d}',inverter_id=f'INV_{i:02d}',model='GW61.4-BAT-AC-G10',nominal_kwh=61.4,usable_catalog_kwh=60.,min_voltage_v=275.52,max_voltage_v=346.56,inverter_input_current_a=50.,charge_kw=12.,discharge_kw=12.,soc_initial=.5,soc_min=.2,soc_max=.95,eta_charge=.95,eta_discharge=.95) for i in [1,2]] if not house else []
    return dict(evse=[dict(id=f'EVSE_{i+1:02d}',model='GW7K-HCA-20' if house else 'GW22K-HCA-20',max_kw=c['evse_kw']) for i in range(c['n_evse'])],
        pv=dict(dc_kwp=c['pv_kwp'],plane='horizontal proxy',noct_c=45.,temperature_coefficient_per_c=-.0035,other_loss_fraction=.14,inverter_efficiency=.97),
        inverters=[dict(id=f'INV_{i+1:02d}',model='GW6000-ES-20' if house else 'GW30K-ET',ac_kw=6. if house else 30.,pv_dc_kwp=5.5 if house else 25.,shared_pv_plus_battery_discharge_ac_kw=6. if house else 30.,battery_input_current_a=120. if house else 50.) for i in range(1 if house else 2)],
        batteries=bat,optional_battery_template=template if house else None,
        grid=dict(import_kw=17. if house else 90.,export_kw=6. if house else 60.,source='simulation assumption'),
        battery_dispatch='NOT_SIMULATED',soc_timeseries='NOT_GENERATED',battery_power_reference='AC bus; DC discharge demand = discharge_kw / eta_discharge',hardware_status='demonstrative nominal envelopes, not certified electrical design')

def solar(profile,b,ev):
    c=PROFILES[profile];_,_,ghi=weather();irr=ghi.reshape(-1,15).mean(axis=1)
    cell=b['temperatura_externa_c'].to_numpy()+irr*(45-20)/800
    dc=c['pv_kwp']*irr/1000*(1-.0035*(cell-25))*.86
    ac=np.minimum(dc*.97,c['inverter_kw'])
    a=pd.DataFrame(dict(ghi_w_m2=irr,pv_available_dc_kw=dc,pv_generation_ac_kw=ac,pv_generation_ac_kwh=ac*.25,pv_clipping_kw=np.maximum(0,dc*.97-ac)),index=INDEX)
    a['weather_available_at']=(INDEX.floor('h')+pd.Timedelta(hours=1)).map(lambda t:t.isoformat())
    for i in range(c['n_evse']):a[f'EVSE_{i+1:02d}_available_fraction']=ev[f'evse_{i+1:02d}_available_fraction']
    for inv in equipment(profile)['inverters']:a[inv['id']+'_available']=1;a[inv['id']+'_shared_ac_limit_kw']=inv['ac_kw']
    for bat in equipment(profile)['batteries']:a[bat['id']+'_available']=1
    a['grid_available']=1
    return a

def plots(out,b,ev,pv,monthly):
    plt.rcParams.update({'font.size':9,'figure.dpi':130})
    fig,ax=plt.subplots(3,3,figsize=(15,11),layout='constrained')
    hour=INDEX.hour+INDEX.minute/60
    for a,label in [(b['consumo_predio_kw'],'Edificação'),(ev['potencia_entregue_kw'],'EV'),(pv['pv_generation_ac_kw'],'PV')]:a.groupby(hour).mean().plot(ax=ax[0,0],label=label)
    ax[0,0].legend();ax[0,0].set(title='Perfil médio diário',ylabel='kW',xlabel='Hora local')
    monthly[['building_kwh','expected_reference_kwh']].set_axis(monthly.index.strftime('%m')).plot.bar(ax=ax[0,1]);ax[0,1].set(title='Edificação: esperado × simulado',ylabel='kWh/mês')
    b['consumo_predio_kwh'].resample('D').sum().groupby(lambda d:d.dayofweek).mean().plot.bar(ax=ax[0,2]);ax[0,2].set(title='Edificação por dia da semana',ylabel='kWh/dia',xlabel='0=seg, 6=dom')
    ev[['potencia_solicitada_kw','potencia_entregue_kw']].plot.hist(ax=ax[1,0],bins=30,logy=True,alpha=.55);ax[1,0].set(title='Demanda EV (inclui zeros)',xlabel='kW')
    ev['ocupacao_media_pct'].groupby(hour).mean().plot(ax=ax[1,1]);ax[1,1].set(title='Ocupação EV média',ylabel='%',xlabel='Hora local')
    ev['carros_chegando'].resample('D').sum().plot(ax=ax[1,2]);ax[1,2].set(title='Chegadas diárias',ylabel='veículos')
    b['consumo_predio_kwh'].resample('D').sum().plot(ax=ax[2,0],label='Edificação');ev['energia_entregue_kwh'].resample('D').sum().plot(ax=ax[2,0],label='EV');ax[2,0].legend();ax[2,0].set(title='Energia diária separada',ylabel='kWh')
    pv['pv_generation_ac_kw'].iloc[:672].plot(ax=ax[2,1]);ax[2,1].set(title='PV: primeira semana sintética',ylabel='kW AC')
    b.loc[(INDEX.hour<6)|(INDEX.hour>=22),'consumo_predio_kw'].resample('D').mean().plot(ax=ax[2,2]);ax[2,2].set(title='Base noturna da edificação',ylabel='kW')
    fig.suptitle(out.name+' — SIMULATED / TMY, não medido em 2025',fontsize=15)
    fig.savefig(out/'diagnostics.png');plt.close(fig)

def generate(profile):
    c=PROFILES[profile];out=DATA/profile;out.mkdir(parents=True,exist_ok=True)
    b,loads=building(profile);ev,sessions,faults=simulate(profile);pv=solar(profile,b,ev)
    for name,a in [('building',b),('ev',ev),('energy',pv)]:
        write_series(a,out/(name+'.csv'),c['station_id'])
        monthdir=out/'monthly';monthdir.mkdir(exist_ok=True)
        for month in range(1,13):write_series(a[a.index.month==month],monthdir/f'{name}_2025-{month:02d}.csv',c['station_id'])
    sessions.to_csv(out/'sessions.csv',index=False,float_format='%.10f')
    faults.insert(0,'station_id',c['station_id']);faults['origin']='SIMULATED'
    faults['start_at']=faults['start_minute'].map(lambda x:(INDEX[0]+pd.Timedelta(minutes=x)).isoformat())
    faults['end_at']=faults['end_minute'].map(lambda x:(INDEX[0]+pd.Timedelta(minutes=x)).isoformat())
    faults.to_csv(out/'equipment_events.csv',index=False)
    monthly=b[['consumo_predio_kwh','cooling_kwh','hvac_fan_kwh','scheduled_kwh']].resample('MS').sum().rename(columns={'consumo_predio_kwh':'building_kwh'})
    monthly['ev_ac_kwh']=ev['energia_entregue_kwh'].resample('MS').sum()
    monthly['pv_ac_kwh']=pv['pv_generation_ac_kwh'].resample('MS').sum()
    monthly['arrivals']=ev['carros_chegando'].resample('MS').sum()
    monthly['expected_base_kwh']=monthly.index.days_in_month*sum(v[2] for v in LOADS[profile].values())
    monthly['expected_reference_kwh']=monthly['expected_base_kwh']+monthly.index.days_in_month*(.75 if c['n_evse']==1 else 37.5)
    monthly['base_deviation_pct']=100*(monthly['scheduled_kwh']/monthly['expected_base_kwh']-1)
    monthly.to_csv(out/'monthly_validation.csv',index_label='month',float_format='%.6f')
    disagg=(loads*.25).resample('MS').sum();disagg['hvac_kwh']=monthly['cooling_kwh']+monthly['hvac_fan_kwh']
    disagg.to_csv(out/'monthly_load_breakdown.csv',index_label='month',float_format='%.6f')
    expected=pd.DataFrame([dict(load=k,expected_annual_kwh=v[2]*365,simulated_annual_kwh=float(loads[k].sum()*.25),deviation_pct=float((loads[k].sum()*.25/(v[2]*365)-1)*100)) for k,v in LOADS[profile].items()])
    expected.to_csv(out/'expected_vs_simulated.csv',index=False,float_format='%.6f')
    # Issue time = current interval end. 48 future full intervals; right bound exclusive.
    split=pd.DataFrame(index=INDEX);split['issue_time']=INDEX+pd.Timedelta(minutes=15)
    split['last_target_end']=INDEX+pd.Timedelta(minutes=15*49)
    split['partition']=np.where(INDEX.month<=8,'train',np.where(INDEX.month<=10,'validation','test'))
    ends=np.where(INDEX.month<=8,'2025-09-01T00:00:00-03:00',np.where(INDEX.month<=10,'2025-11-01T00:00:00-03:00','2026-01-01T00:00:00-03:00'))
    split['eligible_horizon48']=split['last_target_end'].to_numpy()<=pd.to_datetime(ends).to_numpy()
    split['eligible_motor2_history']=np.arange(len(INDEX))>=2688
    write_series(split,out/'training_split_plan.csv',c['station_id'])
    shutil.copy2(ROOT/profile/'run/eplusout.err',out/'energyplus_errors.txt')
    plots(out,b,ev,pv,monthly)
    manifest=dict(station_id=c['station_id'],profile=profile.upper(),version='1.0.0',origin='SIMULATED',calendar_year=2025,
      interval_minutes=15,timestamp='interval_start',available_at='timestamp + 15 minutes',timezone='America/Sao_Paulo',utc_offset='-03:00',rows=len(INDEX),
      location=dict(name='Itirapina/SP — hypothetical site',latitude=-22.25,longitude=-47.82,weather_proxy='Sao Carlos station 868450; regional proxy, not local measurements'),
      building_engine='EnergyPlus 25.2.0-cf7368216c / OpenStudio 3.11.0+241b8abb4d',building_area_m2=c['area'],
      weather=json.loads((ROOT/'weather/source.json').read_text(encoding='utf-8-sig')),equipment=equipment(profile),
      seeds=dict(loads=c['seed'],ev=c['seed']+10),versions=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__),
      evidence=dict(energyplus='Completed Successfully, error log included',original_commit=json.loads((ROOT/'baseline.json').read_text())['commit']),
      ev_semantics=dict(energy='AC-meter kWh; battery gain=0.92*delivered AC',power='15-minute mean; requested=connected vehicles only, before outages, bounded by EV acceptance and EVSE',occupancy='maximum simultaneous connected within interval; mean occupancy separately',queue='max waiting within interval; requests of queued/rejected vehicles only in sessions',sessions='connection held until departure, even after target; timestamps [start,end)',residential_frequency='3-4 arrivals/month; latest user supplement'),
      weather_causality='Hourly source only known at weather_available_at; availability-safe asof or one-hour lag required for weather features. No future TMY as forecast.',
      pv_semantics='horizontal GHI proxy, hourly radiation held over four quarters; clipping only at real AC limit; no dispatch',
      compatibility=dict(current_models='NOT compatible without dedicated adaptation/training; Motor2 fixed4EVSE/88kW, calendar2026, naive timestamps',backend_import='NOT directly importable: current endpoint accepts IMPORTED only; files remain SIMULATED',monthly_shards='each <10000 rows and 8MB; schema/provenance adapter still required'),
      sources=json.loads((ROOT/'sources.json').read_text(encoding='utf-8-sig')),
      inputs_sha256={str(p.relative_to(REPO)).replace('\\','/'):sha(p) for p in [ROOT/profile/'parameters.json',ROOT/profile/'schedules.csv',ROOT/profile/'building.idf',ROOT/profile/'building.osm',next((ROOT/'weather').glob('*.epw')),ROOT/'loads.py',ROOT/'ev.py',ROOT/'build_model.rb',ROOT/'generate.py']},
      outputs_sha256={str(p.relative_to(out)).replace('\\','/'):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'})
    save_json(out/'manifest.json',manifest)
    print(profile,monthly[['building_kwh','ev_ac_kwh','arrivals']].round(2).to_dict(),flush=True)
    return b

def comparison(curves):
    fig,ax=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for name,b in curves.items():
        b['consumo_predio_kwh'].resample('MS').sum().plot(ax=ax[0],label=name,x_compat=True)
        b['consumo_predio_kw'].groupby(INDEX.hour).mean().plot(ax=ax[1],label=name)
    ax[0].set(ylabel='kWh/mês',title='Escalas físicas: edificação sem EV');ax[1].set(ylabel='kW',title='Perfil médio por hora');ax[0].legend();ax[1].legend()
    fig.savefig(DATA/'comparison.png');plt.close(fig)

if __name__=='__main__':
    comparison({p:generate(p) for p in PROFILES})
