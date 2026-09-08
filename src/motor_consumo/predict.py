"""Uma única chamada para 48 previsões usando o seletor congelado em maio."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
import lightgbm as lgb
import pandas as pd
from motor_consumo.features import *


class MotorHibrido:
    def __init__(self,model_dir=MODELS):
        self.folder=Path(model_dir)
        self.metadata=json.loads((self.folder/'metadata.json').read_text(encoding='utf-8'))
        selector_path=self.folder/'selector.json'
        if hashlib.sha256(selector_path.read_bytes()).hexdigest()!=self.metadata['selector_sha256']:
            raise ValueError('Seletor modificado após o treino.')
        selector=json.loads(selector_path.read_text(encoding='utf-8'))
        self.selection=selector['horizons']
        if [r['horizon'] for r in self.selection]!=list(HORIZONS) or any(r['method'] not in METHODS for r in self.selection):
            raise ValueError('Seletor incompleto ou inválido.')
        self.models={}
        for row in self.selection:
            h=row['horizon']; method=row['method']
            if method=='residual_v2':
                record=self.metadata['models'][h-1]
                path=self.folder/record['file']; expected=record['sha256']
            elif method=='lightgbm_v1':
                path=V1_MODELS/f'horizon_{h:02d}.txt'
                expected=self.metadata['v1_model_hashes'][path.name]
            else:
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError(f'Modelo alterado: {path}')
            self.models[h]=lgb.Booster(model_file=str(path))

    def predict(self,history,timestamp=None):
        data=history.copy()
        if 'timestamp' in data:
            data['timestamp']=pd.to_datetime(data.timestamp); data=data.set_index('timestamp')
        origin=pd.Timestamp(timestamp) if timestamp is not None else data.index.max()
        data=validate_frame(data.loc[data.index<=origin])
        if data.index[-1]!=origin or len(data)<MIN_HISTORY:
            raise ValueError(f'É necessário terminar no timestamp solicitado e ter {MIN_HISTORY} linhas contínuas.')
        data=data.iloc[-MIN_HISTORY:]
        base=residual_base(data); v1base=historical_features(data)
        result=[]
        for row in self.selection:
            h=row['horizon']; method=row['method']
            if method=='persistencia':
                value=float(data.consumo_predio_kw.iloc[-1])
            elif method=='semana_anterior':
                value=float(weekly_baseline(data,h).iloc[-1])
            else:
                x=(residual_features(data,h,base) if method=='residual_v2' else horizon_features(data,h,v1base)).iloc[[-1]]
                if x.isna().any().any(): raise ValueError('Features incompletas.')
                value=float(self.models[h].predict(x,num_threads=2)[0])
                if method=='residual_v2': value+=float(weekly_baseline(data,h).iloc[-1])
            result.append({'timestamp_previsto':origin+h*STEP,'consumo_previsto_kw':max(0.0,value)})
        prediction=pd.DataFrame(result)
        prediction.attrs.update(timestamp_ultima_medicao=str(origin),disponivel_em=str(origin+STEP),
                                metodos=[r['method'] for r in self.selection])
        return prediction


def predict(history,timestamp=None,model_dir=MODELS):
    return MotorHibrido(model_dir).predict(history,timestamp)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=SOURCE)
    parser.add_argument('--timestamp',required=True)
    parser.add_argument('--output',type=Path,default=OUTPUT/'previsao_hibrida_48.csv')
    args=parser.parse_args()
    result=predict(pd.read_csv(args.data),args.timestamp)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(args.output,index=False,float_format='%.9f')
    print(result.to_string(index=False))
