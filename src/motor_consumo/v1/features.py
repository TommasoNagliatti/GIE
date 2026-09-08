"""Validação e features causais compartilhadas entre treino e inferência."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT/'data'/'consumo_predio_6_meses.csv'
MODELS = ROOT/'models'/'consumo_predio'/'v1'
OUTPUT = ROOT/'outputs'/'motor_consumo'/'v1'
STEP = pd.Timedelta(minutes=15)
HORIZONS = range(1,49)
REQUIRED = ['consumo_predio_kw','temperatura_externa_c','umidade_relativa_pct']
LAGS = [1,2,4,8,12,24,48,96,672]
WINDOWS = [4,12,24,96]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def validate_frame(frame):
    data = frame.copy()
    if 'timestamp' in data.columns:
        data['timestamp'] = pd.to_datetime(data.timestamp,errors='raise')
        data = data.set_index('timestamp')
    if not isinstance(data.index,pd.DatetimeIndex):
        raise ValueError('É necessário timestamp ou DatetimeIndex.')
    if data.index.tz is not None:
        raise ValueError('Use timestamps locais sem offset, conforme o CSV (UTC-3).')
    if len(data)==0 or data.index.hasnans or not data.index.is_unique:
        raise ValueError('Histórico vazio, timestamps ausentes ou duplicados.')
    if not data.index.is_monotonic_increasing:
        raise ValueError('Timestamps fora de ordem; não serão reordenados silenciosamente.')
    if not data.index.equals(pd.date_range(data.index[0],periods=len(data),freq='15min')):
        raise ValueError('Lacunas ou intervalo diferente de 15 minutos.')
    if not ((data.index.minute%15==0)&(data.index.second==0)&(data.index.microsecond==0)).all():
        raise ValueError('Timestamps não alinhados aos quartos de hora.')
    missing = set(REQUIRED)-set(data.columns)
    if missing:
        raise ValueError(f'Colunas ausentes: {missing}')
    for col in data.columns:
        data[col] = pd.to_numeric(data[col],errors='raise')
    if not np.isfinite(data.to_numpy()).all():
        raise ValueError('Valores ausentes ou não finitos; não há imputação automática.')
    if (data.consumo_predio_kw<0).any():
        raise ValueError('Consumo negativo.')
    if not data.umidade_relativa_pct.between(0,100).all():
        raise ValueError('Umidade fora de 0–100%.')
    if 'consumo_predio_kwh' in data:
        if (data.consumo_predio_kwh<0).any() or not np.allclose(data.consumo_predio_kwh,.25*data.consumo_predio_kw,atol=1e-6):
            raise ValueError('Energia negativa ou incoerente com a potência de 15 min.')
    # Negative temperatures are physically valid; do not reject them.
    return data


def load_data(path=SOURCE):
    return validate_frame(pd.read_csv(path))


def audit_source(path=SOURCE):
    path=Path(path)
    data=load_data(path)
    expected=pd.date_range('2026-01-01','2026-07-01',freq='15min',inclusive='left')
    if not data.index.equals(expected):
        raise ValueError('O CSV oficial não corresponde a janeiro–junho de 2026 completo.')
    audit={'source_path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
           'rows':len(data),'first':str(data.index[0]),'last':str(data.index[-1]),
           'interval_minutes':15,'duplicates':0,'missing_values':0,'negative_consumption':0,
           'continuous':True,'raw_rows_by_month':data.groupby(data.index.month).size().to_dict(),
           'range_kw':[float(data.consumo_predio_kw.min()),float(data.consumo_predio_kw.max())],
           'timestamp_semantics':'início do intervalo; a linha t está disponível em t+15min; UTC-3',
           'source_modified':False}
    write_json(OUTPUT/'dataset_validation.json',audit)
    return data,audit


def calendar(index,prefix):
    hour=index.hour+index.minute/60
    return {prefix+'hora':hour,prefix+'dia_semana':index.dayofweek,
            prefix+'fim_de_semana':(index.dayofweek>=5).astype(int),prefix+'mes':index.month,
            prefix+'hora_sin':np.sin(2*np.pi*hour/24),prefix+'hora_cos':np.cos(2*np.pi*hour/24),
            prefix+'semana_sin':np.sin(2*np.pi*index.dayofweek/7),prefix+'semana_cos':np.cos(2*np.pi*index.dayofweek/7)}


def historical_features(data):
    y=data.consumo_predio_kw
    columns={'consumo_atual_kw':y}
    for lag in LAGS:
        columns[f'consumo_lag_{lag*15}m']=y.shift(lag)
    # Trailing windows include the last OBSERVED interval t, never t+1.
    for window in WINDOWS:
        rolling=y.rolling(window,min_periods=window)
        for stat in ['mean','min','max','std']:
            columns[f'consumo_{stat}_{window*15}m']=getattr(rolling,stat)()
    for col in ['temperatura_externa_c','umidade_relativa_pct']:
        columns[col+'_atual']=data[col]
        for lag in [1,4,12,24,48,96]:
            columns[f'{col}_lag_{lag*15}m']=data[col].shift(lag)
        for window in WINDOWS:
            columns[f'{col}_media_{window*15}m']=data[col].rolling(window,min_periods=window).mean()
    columns.update(calendar(data.index,'origem_'))
    return pd.DataFrame(columns,index=data.index)


def horizon_features(data,h,base=None):
    if h not in HORIZONS:
        raise ValueError('Horizonte deve estar entre 1 e 48.')
    x=historical_features(data) if base is None else base.copy()
    for name,value in calendar(data.index+h*STEP,'alvo_').items():
        x[name]=value
    # Historical readings at the target's same clock time. Since h<=48,
    # both offsets remain positive and are known at origin t.
    x['consumo_alvo_dia_anterior']=data.consumo_predio_kw.shift(96-h)
    x['consumo_alvo_semana_anterior']=data.consumo_predio_kw.shift(672-h)
    return x


def target_name(h):
    return f'target_{h//4}h' if h%4==0 else f'target_{h*15}m'


def targets(data):
    return pd.DataFrame({target_name(h):data.consumo_predio_kw.shift(-h) for h in HORIZONS},index=data.index)


def split_masks(data,base):
    index=data.index
    # Identical forecast origins for all 48 horizons. Purge the final 48
    # origins of each partition so that NO target crosses its boundary.
    valid=base.notna().all(axis=1).to_numpy()
    boundaries={'train':('2026-01-01','2026-05-01'),
                'validation':('2026-05-01','2026-06-01'),
                'test':('2026-06-01','2026-07-01')}
    return {name:valid&(index>=pd.Timestamp(start))&(index+48*STEP<pd.Timestamp(end))
            for name,(start,end) in boundaries.items()}


if __name__=='__main__':
    _,result=audit_source()
    print(json.dumps(result,ensure_ascii=False,indent=2))
