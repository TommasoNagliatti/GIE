"""Pré-treino: causalidade, fronteiras e métricas, sem usar junho."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_carregadores.features import *
from motor_carregadores.metrics import classification
def run():
    raw=pd.read_csv(SOURCE);d=validate_frame(raw.loc[raw.timestamp<'2026-06-01'])
    base=historical_features(d)
    for t in pd.date_range('2026-05-01 07:45','2026-05-30 07:45',freq='3D'):
        past=d.loc[:t].iloc[-MIN_HISTORY:];bp=historical_features(past)
        poison=d.copy();poison.loc[poison.index>t,:]=1e9;bpoison=historical_features(poison)
        for h in [1,4,12,24,48]:
            a=horizon_features(d,h,base).loc[t]
            pd.testing.assert_series_equal(a,horizon_features(past,h,bp).loc[t],check_exact=True)
            pd.testing.assert_series_equal(a,horizon_features(poison,h,bpoison).loc[t],check_exact=True)
            expected=np.mean([d.loc[t+h*STEP-pd.Timedelta(days=7*k),'potencia_solicitada_kw'] for k in range(1,5)])
            assert abs(power_baselines(d,h)['media_4semanas'].loc[t]-expected)<1e-10
    for name,end in [('train','2026-05-01'),('validation','2026-06-01')]:
        ix=d.index[partition_mask(d,name)];assert (ix+48*STEP<pd.Timestamp(end)).all()
    perfect=classification([0,1,0,1],[.1,.9,.2,.8]);assert perfect['pr_auc']==1 and perfect['roc_auc']==1 and perfect['f1']==1
    ties=classification([0,1,0,1],[.5]*4);assert ties['roc_auc']==.5 and ties['average_precision']==.5
    write_json(OUTPUT/'preflight_validation.json',{'passed':True,'future_invariance_checks':50,'bounded_history_matches_exactly':True,'weekly_references':True,'purged_boundaries':True,'classification_metrics_checks':True,'june_used':False,'feature_count':horizon_features(d,1,base).shape[1]})
    print('Pré-treino: causalidade, histórico limitado, referências semanais e métricas OK.')
if __name__=='__main__':run()
