"""Inferência com histórico disponível: predict(history, timestamp, model_dir)."""
if __package__ in (None,''):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import lightgbm as lgb
from motor_consumo.v1.features import (SOURCE,MODELS,OUTPUT,STEP,HORIZONS,
                                    validate_frame,historical_features,horizon_features)


class MotorConsumo:
    """Carregue uma vez e reutilize a cada novo intervalo observado."""
    def __init__(self,model_dir=MODELS):
        folder=Path(model_dir)
        self.metadata=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        self.models=[lgb.Booster(model_file=str(folder/item['file'])) for item in self.metadata['models']]
        if len(self.models)!=48:
            raise ValueError('Motor incompleto: são necessários 48 modelos.')

    def predict(self,history,timestamp=None):
        """timestamp é o início da última linha já medida (disponível em t+15min).

        O futuro é descartado ANTES da validação e geração das features. Os
        48 timestamps retornados são os inícios dos próximos intervalos.
        """
        history=history.copy()
        if 'timestamp' in history.columns:
            history['timestamp']=pd.to_datetime(history.timestamp)
            history=history.set_index('timestamp')
        origin=pd.Timestamp(timestamp) if timestamp is not None else history.index.max()
        past=history.loc[history.index<=origin]
        past=validate_frame(past)
        if past.index[-1]!=origin:
            raise ValueError('Não há medição no timestamp solicitado.')
        if len(past)<self.metadata['minimum_history_rows']:
            raise ValueError('Necessárias pelo menos 673 linhas contínuas: 7 dias + intervalo atual.')
        past=past.iloc[-673:]
        base=historical_features(past)
        values=[]
        for h,model in zip(HORIZONS,self.models):
            row=horizon_features(past,h,base).iloc[[-1]][self.metadata['feature_names']]
            if row.isna().any().any():
                raise ValueError('Features indisponíveis no histórico.')
            values.append(max(0.0,float(model.predict(row,num_threads=2)[0])))
        result=pd.DataFrame({'timestamp_previsto':[origin+h*STEP for h in HORIZONS],
                             'consumo_previsto_kw':values})
        result.attrs.update(timestamp_ultima_medicao=str(origin),disponivel_em=str(origin+STEP),timezone='UTC-03:00')
        return result


def predict(history,timestamp=None,model_dir=MODELS):
    return MotorConsumo(model_dir).predict(history,timestamp)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=SOURCE)
    parser.add_argument('--timestamp',required=True,help='Início do último intervalo já observado.')
    parser.add_argument('--output',type=Path,default=OUTPUT/'previsao_12h.csv')
    args=parser.parse_args()
    result=predict(pd.read_csv(args.data),args.timestamp)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result.to_csv(args.output,index=False,float_format='%.6f')
    print(result.to_string(index=False))
