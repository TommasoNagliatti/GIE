"""Produção: uma chamada, cinco modelos carregados uma vez, 48 intervalos."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
import lightgbm as lgb
from motor_carregadores.features import *
class MotorCarregadores:
    def __init__(self,model_dir=MODELS):
        self.folder=Path(model_dir);self.meta=json.loads((self.folder/'metadata.json').read_text(encoding='utf-8'))
        if digest(self.folder/'config.json')!=self.meta['config_sha256']:raise ValueError('Configuração alterada.')
        self.models={}
        for row in self.meta['models']:
            p=self.folder/row['file']
            if digest(p)!=row['sha256']:raise ValueError('Modelo alterado: '+row['name'])
            self.models[row['name']]=lgb.Booster(model_file=str(p))
    def predict(self,history,timestamp=None):
        d=history.copy()
        if 'timestamp' in d:
            d.index=pd.DatetimeIndex(pd.to_datetime(d.pop('timestamp')),name='timestamp')
        origin=pd.Timestamp(timestamp) if timestamp is not None else d.index.max()
        d=validate_frame(d.loc[d.index<=origin])
        if d.index[-1]!=origin or len(d)<MIN_HISTORY:raise ValueError(f'Necessárias {MIN_HISTORY} linhas até a origem solicitada.')
        d=d.iloc[-MIN_HISTORY:];base=historical_features(d)
        x=pd.concat([horizon_features(d,h,base).iloc[[-1]] for h in HORIZONS],ignore_index=True)[self.meta['features']]
        if x.isna().any().any():raise ValueError('Features incompletas.')
        weekly=np.array([power_baselines(d,h)['media_4semanas'].iloc[-1] for h in HORIZONS])
        p={name:m.predict(x,num_threads=2) for name,m in self.models.items()}
        power=np.clip(weekly+p['power'],0,88)
        result=pd.DataFrame({'timestamp_previsto':[origin+h*STEP for h in HORIZONS],
            'potencia_solicitada_prevista_kw':power,'energia_solicitada_prevista_kwh':power*.25,
            'carregadores_ocupados_previstos':np.clip(p['occupancy'],0,4),
            'carros_chegando_previstos':np.clip(p['arrivals'],0,6),
            'carros_na_fila_previstos':np.clip(p['queue'],0,3),'probabilidade_fila':np.clip(p['risk'],0,1)})
        result.attrs.update(timestamp_ultima_medicao=str(origin),disponivel_em=str(origin+STEP))
        return result
def predict(history,timestamp=None,model_dir=MODELS):return MotorCarregadores(model_dir).predict(history,timestamp)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=SOURCE);p.add_argument('--timestamp',required=True)
    p.add_argument('--output',type=Path,default=OUTPUT/'previsao_48.csv');a=p.parse_args()
    result=predict(pd.read_csv(a.data),a.timestamp);a.output.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(a.output,index=False,float_format='%.8f');print(result.to_string(index=False))
