"""Versioned adapter. Local artifact loading only, not a multi-station service."""
import re
import lightgbm as lgb
from .core import *
class Forecaster:
    def __init__(self,station_id,version='v1',model_root=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',station_id) or not re.fullmatch(r'[A-Za-z0-9_-]+',version):raise ValueError('Invalid station/version')
        self.folder=Path(model_root or ROOT/'models/stations')/station_id/version
        self.freeze=json.loads((self.folder/'freeze.json').read_text(encoding='utf-8'))
        if self.freeze['station_id']!=station_id:raise ValueError('Station artifact mismatch')
        for name,h in self.freeze['files'].items():
            if digest(self.folder/name)!=h:raise ValueError('Artifact integrity failure: '+name)
        self.c=json.loads((self.folder/'config.json').read_text(encoding='utf-8'))
        if self.c['station_id']!=station_id:raise ValueError('Config station mismatch')
        self.meta=json.loads((self.folder/'metadata.json').read_text(encoding='utf-8'));self.selection=json.loads((self.folder/'selection.json').read_text(encoding='utf-8'))
        self.freq=json.loads((self.folder/'frequency.json').read_text(encoding='utf-8'))
        self.models={k:lgb.Booster(model_file=str(self.folder/v['file'])) if 'file' in v else v['constant'] for k,v in self.meta['models'].items()}
    def head(self,key,x):
        m=self.models[key]
        return m.predict(x,num_threads=2) if isinstance(m,lgb.Booster) else np.full(len(x),m)
    def candidates(self,d,positions):
        x,o,h,target=features(d,self.c,positions)
        if list(x.columns)!=self.meta['feature_names']:raise ValueError('Feature schema mismatch')
        ev,qfreq=baselines(d,self.c,o,h,target,self.freq)
        b={k:v[:,0] for k,v in ev.items() if k in ['persistence','previous_day','previous_week']}
        for leaves in [15,31]:b[f'lightgbm_{leaves}']=np.maximum(0,self.head(f'building_{leaves}',x))
        p=np.zeros((len(x),7))
        for j,key in enumerate(TARGETS[1:],1):p[:,j]=self.head(key,x)
        ev['lightgbm']=bound(p,self.c)
        q={'frequency':qfreq,'lightgbm':np.clip(self.head('q90',x),0,self.c['ev_limit_kw'])}
        return b,ev,q,o,h,target
    def predict(self,building,ev,issue_time):
        issue=pd.Timestamp(issue_time)
        if issue.tzinfo is None:raise ValueError('Issue time must carry timezone')
        issue=issue.tz_convert(self.c['timezone']);step=pd.Timedelta(minutes=self.c['step_minutes'])
        # Reject caller-supplied future observations; never silently accept a full future frame.
        d=validate(building,ev,self.c)
        if d.index[-1]+step!=issue:raise ValueError('Stale/future history: last interval must end at issuance')
        d=d.iloc[-self.c['minimum_history']:]
        b,e,q,o,h,target=self.candidates(d,[len(d)-1]);sel=self.selection;p=e[sel['motor2']];raw=q[sel['q90']]
        result=pd.DataFrame(dict(timestamp_previsto=target,consumo_previsto_kw=b[sel['motor1']],
          potencia_solicitada_prevista_kw=p[:,1],potencia_solicitada_alta_kw=np.maximum(p[:,1],raw),energia_solicitada_prevista_kwh=p[:,1]*self.c['step_minutes']/60,
          carregadores_ocupados_previstos=p[:,2],carros_chegando_previstos=p[:,3],carros_na_fila_previstos=p[:,4],probabilidade_fila=p[:,5],
          probabilidade_recarga=p[:,6],potencia_q90_bruta_kw=raw))
        result.attrs.update(station_id=self.c['station_id'],issue_time=issue.isoformat(),schema=self.c['schema'],origin='SIMULATED',event_threshold=sel['event_threshold'])
        return result
