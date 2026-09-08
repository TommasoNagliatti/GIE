"""Features residuais causais; a implementação V1 é importada somente para leitura."""
from pathlib import Path
import numpy as np
import pandas as pd
from motor_consumo.v1.features import (ROOT,SOURCE,STEP,HORIZONS,load_data,validate_frame,
    historical_features,horizon_features,split_masks,write_json)

MODELS=ROOT/'models'/'consumo_predio'/'v2'
OUTPUT=ROOT/'outputs'/'motor_consumo'/'v2'
V1_MODELS=ROOT/'models'/'consumo_predio'/'v1'
MIN_HISTORY=768  # lag semanal de 672 + janela completa de 96 registros
METHODS=['persistencia','semana_anterior','lightgbm_v1','residual_v2']
PARAMS={'objective':'regression','metric':'l1','learning_rate':0.05,'num_leaves':15,
        'min_data_in_leaf':40,'lambda_l2':1.0,'feature_fraction':1.0,'bagging_fraction':1.0,
        'seed':20260905,'num_threads':2,'deterministic':True,'force_col_wise':True,'verbosity':-1}


def residual_base(data):
    base=historical_features(data)
    y=data.consumo_predio_kw
    difference=y-y.shift(672)
    extra={'consumo_diferenca_semana_atual':difference,
           'consumo_razao_semana_atual':y/(y.shift(672).abs()+1),
           'consumo_diferenca_dia_atual':y-y.shift(96)}
    for lag in [1,4,12,24]:
        extra[f'tendencia_consumo_{lag*15}m']=y-y.shift(lag)
    for window in [4,12,24,96]:
        extra[f'correcao_semanal_media_{window*15}m']=difference.rolling(window,min_periods=window).mean()
        extra[f'correcao_semanal_std_{window*15}m']=difference.rolling(window,min_periods=window).std()
    for col in ['temperatura_externa_c','umidade_relativa_pct']:
        extra[col+'_diferenca_semana_atual']=data[col]-data[col].shift(672)
        extra[col+'_tendencia_1h']=data[col]-data[col].shift(4)
    return pd.concat([base,pd.DataFrame(extra,index=data.index)],axis=1)


def residual_features(data,h,base=None):
    return horizon_features(data,h,residual_base(data) if base is None else base)


def weekly_baseline(data,h):
    return data.consumo_predio_kw.shift(672-h)


def residual_target(data,h):
    return data.consumo_predio_kw.shift(-h)-weekly_baseline(data,h)


def masks_for(data,base):
    masks=split_masks(data,base)
    masks['diagnostic_june']=masks.pop('test')
    return masks


def select_methods(validation_scores):
    if set(validation_scores.partition)!= {'validation'}:
        raise ValueError('O seletor aceita exclusivamente a validação de maio.')
    if set(validation_scores.method)!=set(METHODS):
        raise ValueError('São necessários os quatro candidatos.')
    rows=[]
    for h in HORIZONS:
        part=validation_scores[validation_scores.horizon==h].copy()
        if len(part)!=4 or part.method.nunique()!=4 or not np.isfinite(part.mae_kw).all():
            raise ValueError(f'Candidatos inválidos para horizonte {h}.')
        part['tie_order']=part.method.map({m:i for i,m in enumerate(METHODS)})
        best=part.sort_values(['mae_kw','tie_order']).iloc[0]
        rows.append({'horizon':h,'minutes':h*15,'method':best.method,'validation_mae_kw':float(best.mae_kw)})
    return rows
