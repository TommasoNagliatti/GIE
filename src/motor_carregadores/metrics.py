"""Métricas sem dependências adicionais; PR-AUC trapezoidal e AP separadas."""
import numpy as np
import pandas as pd
def regression(y,p):
    y=np.asarray(y,dtype=float);p=np.asarray(p,dtype=float);e=p-y
    return {'mae':float(np.abs(e).mean()),'rmse':float(np.sqrt(np.mean(e*e))),
        'wape_pct':float(100*np.abs(e).sum()/np.abs(y).sum()) if np.abs(y).sum() else None,'bias':float(e.mean()),'n':len(y)}
def classification(y,p,threshold=.5):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float); pred=p>=threshold
    tp=int(np.sum(pred&(y==1)));fp=int(np.sum(pred&(y==0)));fn=int(np.sum(~pred&(y==1)))
    precision=tp/(tp+fp) if tp+fp else 0.; recall=tp/(tp+fn) if tp+fn else 0.
    positives=int(y.sum());negatives=len(y)-positives
    order=np.argsort(-p,kind='stable');sy=y[order];sp=p[order]
    ends=np.r_[np.flatnonzero(np.diff(sp)),len(sp)-1]
    tps=np.cumsum(sy)[ends];fps=1+ends-tps
    rec=np.r_[0,tps/positives] if positives else np.zeros(len(ends)+1)
    prec=np.r_[1,tps/(tps+fps)]
    ranks=pd.Series(p).rank(method='average').to_numpy()
    auc=float((ranks[y==1].sum()-positives*(positives+1)/2)/(positives*negatives)) if positives and negatives else None
    return {'pr_auc':float(np.trapezoid(prec,rec)) if positives else None,
        'average_precision':float(np.sum(np.diff(rec)*prec[1:])) if positives else None,'roc_auc':auc,
        'brier_score':float(np.mean((p-y)**2)),'precision':precision,'recall':recall,
        'f1':2*precision*recall/(precision+recall) if precision+recall else 0.,'threshold':float(threshold),
        'prevalence':float(y.mean()),'tp':tp,'fp':fp,'fn':fn,'n':len(y)}
def choose_threshold(y,p):
    rows=[]
    for threshold in np.linspace(.05,.95,91):
        pred=p>=threshold;tp=np.sum(pred&(y==1));fp=np.sum(pred&(y==0));fn=np.sum(~pred&(y==1))
        rows.append({'threshold':float(threshold),'f1':float(2*tp/(2*tp+fp+fn)) if 2*tp+fp+fn else 0.})
    return max(rows,key=lambda r:(r['f1'],-r['threshold'])),rows
