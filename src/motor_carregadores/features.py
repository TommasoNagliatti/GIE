"""Features causais do Motor 2. Timestamp t: início do último intervalo observado."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'data/demanda_carregadores_6_meses.csv'
MODELS=ROOT/'models/carregadores/v1'
OUTPUT=ROOT/'outputs/motor_carregadores/v1'
STEP=pd.Timedelta(minutes=15)
HORIZONS=range(1,49)
MIN_HISTORY=2689
VARIABLES=['potencia_solicitada_kw','potencia_entregue_kw','carregadores_ocupados','carros_conectados','carros_chegando','carros_na_fila','ocupacao_pct','energia_entregue_kwh']
TARGETS={'power':'potencia_solicitada_kw','occupancy':'carregadores_ocupados','arrivals':'carros_chegando','queue':'carros_na_fila'}
LIMITS={'power':88.,'occupancy':4.,'arrivals':6.,'queue':3.}
LAGS=[1,2,4,8,12,24,48,96,672,1344,2016,2688]
WINDOWS=[4,12,24,96]
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def validate_frame(frame):
    d=frame.copy()
    if 'timestamp' in d: d.index=pd.DatetimeIndex(pd.to_datetime(d.pop('timestamp'),errors='raise'),name='timestamp')
    if not isinstance(d.index,pd.DatetimeIndex) or len(d)==0: raise ValueError('Histórico vazio ou sem timestamps.')
    ix=d.index
    if ix.tz is not None or ix.hasnans or not ix.is_unique or not ix.equals(pd.date_range(ix[0],periods=len(ix),freq='15min')): raise ValueError('Timestamps inválidos, duplicados ou descontínuos.')
    if not ((ix.minute%15==0)&(ix.second==0)&(ix.microsecond==0)).all(): raise ValueError('Intervalos desalinhados.')
    if set(VARIABLES)-set(d): raise ValueError('Colunas obrigatórias ausentes.')
    for c in VARIABLES: d[c]=pd.to_numeric(d[c],errors='raise')
    if not np.isfinite(d[VARIABLES].to_numpy()).all() or (d[VARIABLES]<0).any().any(): raise ValueError('Valores inválidos.')
    bounds={'carregadores_ocupados':4,'carros_conectados':4,'carros_chegando':6,'carros_na_fila':3,'ocupacao_pct':100,'potencia_solicitada_kw':88,'potencia_entregue_kw':88}
    for c,limit in bounds.items():
        if d[c].gt(limit+1e-7).any(): raise ValueError('Limite excedido: '+c)
    for c in ['carregadores_ocupados','carros_conectados','carros_chegando','carros_na_fila']:
        if not np.equal(d[c],np.floor(d[c])).all(): raise ValueError('Contagem não inteira: '+c)
    if not np.allclose(d.ocupacao_pct,d.carregadores_ocupados*25,atol=1e-7): raise ValueError('Ocupação incoerente.')
    if not np.array_equal(d.carregadores_ocupados,d.carros_conectados): raise ValueError('Conexões incoerentes.')
    if not np.allclose(d.energia_entregue_kwh,d.potencia_entregue_kw*.25,atol=1e-7): raise ValueError('Energia incoerente.')
    if d.potencia_entregue_kw.gt(d.potencia_solicitada_kw+1e-7).any(): raise ValueError('Entrega maior que solicitação.')
    return d
def load_data(): return validate_frame(pd.read_csv(SOURCE))
def calendar(ix,prefix):
    hr=ix.hour+ix.minute/60; dow=ix.dayofweek
    return {prefix+'hora':ix.hour,prefix+'slot':ix.hour*4+ix.minute//15,prefix+'minuto':ix.minute,
        prefix+'dia_semana':dow,prefix+'fim_de_semana':(dow>=5).astype(int),prefix+'mes':ix.month,
        prefix+'hora_sin':np.sin(2*np.pi*hr/24),prefix+'hora_cos':np.cos(2*np.pi*hr/24),
        prefix+'semana_sin':np.sin(2*np.pi*dow/7),prefix+'semana_cos':np.cos(2*np.pi*dow/7)}
def historical_features(data):
    columns={}
    for c in VARIABLES:
        s=data[c];columns[c+'_atual']=s
        for lag in LAGS: columns[f'{c}_lag_{lag}']=s.shift(lag)
        for w in WINDOWS:
            rolling=s.rolling(w,min_periods=w)
            columns[f'{c}_mean_{w}']=rolling.mean()
            if c in TARGETS.values():
                for stat in ['min','max','std']: columns[f'{c}_{stat}_{w}']=getattr(rolling,stat)()
    columns.update(calendar(data.index,'origem_'))
    # Numerical quantization stabilizes full-series vs bounded-history rolling.
    return pd.DataFrame(columns,index=data.index).round(5).astype('float32')
def horizon_features(data,h,base=None):
    if h not in HORIZONS: raise ValueError('Horizonte inválido.')
    x=(historical_features(data) if base is None else base).copy()
    x['horizonte_minutos']=h*15
    for c,v in calendar(data.index+h*STEP,'alvo_').items(): x[c]=v
    for c in TARGETS.values():
        x[c+'_alvo_dia']=data[c].shift(96-h)
        x[c+'_alvo_semana']=data[c].shift(672-h)
        x[c+'_alvo_4semanas']=sum(data[c].shift(672*k-h) for k in range(1,5))/4
    return x.round(5).astype('float32')
def power_baselines(data,h):
    s=data.potencia_solicitada_kw
    return {'persistencia':s,'dia_anterior':s.shift(96-h),'semana_anterior':s.shift(672-h),
        'media_4semanas':sum(s.shift(672*k-h) for k in range(1,5))/4}
def partition_mask(data,partition):
    start,end={'train':('2026-01-01','2026-05-01'),'validation':('2026-05-01','2026-06-01'),'test':('2026-06-01','2026-07-01')}[partition]
    ix=data.index
    return (np.arange(len(data))>=MIN_HISTORY-1)&(ix>=pd.Timestamp(start))&(ix+48*STEP<pd.Timestamp(end))
def make_long(data,partition):
    mask=partition_mask(data,partition); base=historical_features(data)
    blocks=[]; labels=[]; references=[];origins=[];targets=[];hs=[]
    for h in HORIZONS:
        blocks.append(horizon_features(data,h,base).loc[mask])
        labels.append(data[list(TARGETS.values())].shift(-h).loc[mask].to_numpy())
        references.append(pd.DataFrame(power_baselines(data,h)).loc[mask].to_numpy())
        origins.extend(data.index[mask]);targets.extend(data.index[mask]+h*STEP);hs.extend([h]*int(mask.sum()))
    x=pd.concat(blocks,ignore_index=True)
    y=np.concatenate(labels); b=np.concatenate(references)
    if x.isna().any().any() or not np.isfinite(y).all() or not np.isfinite(b).all(): raise ValueError('Features/targets incompletos.')
    info=pd.DataFrame({'timestamp_origem':origins,'timestamp_previsto':targets,'horizon':hs})
    return x,y,b,info
