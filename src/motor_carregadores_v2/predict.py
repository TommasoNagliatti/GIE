"""Produção V2: mesma V1 para contagens/risco; potência híbrida e limite Q90."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import lightgbm as lgb
from motor_carregadores_v2.features import *
from motor_carregadores.predict import MotorCarregadores as MotorV1
class MotorCarregadores:
    def __init__(self,model_dir=MODELS):
        folder=Path(model_dir);self.meta=json.loads((folder/'metadata.json').read_text())
        assert digest(folder/'selector.json')==self.meta['selector_sha256']
        assert digest(folder/'power_q90.txt')==self.meta['quantile_sha256']
        for name,h in self.meta['v1_files'].items():
            if digest(V1_MODELS/name)!=h:raise ValueError('Dependência V1 alterada: '+name)
        self.v1=MotorV1();self.quantile=lgb.Booster(model_file=str(folder/'power_q90.txt'))
        self.selection=json.loads((folder/'selector.json').read_text())['horizons']
        if [r['horizon'] for r in self.selection]!=list(HORIZONS):raise ValueError('Seletor incompleto.')
    def predict(self,history,timestamp=None):
        result=self.v1.predict(history,timestamp)
        origin=pd.Timestamp(result.attrs['timestamp_ultima_medicao'])
        data=history.copy()
        if 'timestamp' in data:data.index=pd.DatetimeIndex(pd.to_datetime(data.pop('timestamp')),name='timestamp')
        data=validate_frame(data.loc[data.index<=origin]).iloc[-MIN_HISTORY:]
        base=historical_features(data)
        x=pd.concat([horizon_features(data,h,base).iloc[[-1]] for h in HORIZONS],ignore_index=True)[self.meta['features']]
        point=[]
        for i,row in enumerate(self.selection):
            method=row['method']
            value=result.potencia_solicitada_prevista_kw.iloc[i] if method=='residual_v1' else power_baselines(data,row['horizon'])[method].iloc[-1]
            point.append(value)
        point=np.clip(point,0,88);q=np.clip(self.quantile.predict(x,num_threads=2),0,88)
        result['potencia_solicitada_prevista_kw']=point
        result.insert(2,'potencia_solicitada_alta_kw',np.maximum(point,q))
        result['energia_solicitada_prevista_kwh']=point*.25
        return result
def predict(history,timestamp=None,model_dir=MODELS):return MotorCarregadores(model_dir).predict(history,timestamp)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=SOURCE);p.add_argument('--timestamp',required=True)
    p.add_argument('--output',type=Path,default=OUTPUT/'previsao_48.csv');a=p.parse_args()
    result=predict(pd.read_csv(a.data),a.timestamp);a.output.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(a.output,index=False,float_format='%.8f');print(result.to_string(index=False))
