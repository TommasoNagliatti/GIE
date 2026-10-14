import numpy as np

def regression(y,p):
    if len(y)==0:return dict(n=0,mae=None,rmse=None,wape=None)
    error=p-y;den=float(np.abs(y).sum())
    return dict(n=len(y),mae=float(np.abs(error).mean()),rmse=float(np.sqrt(np.mean(error**2))),wape=float(np.abs(error).sum()/den) if den>0 else None)

def detection(y,prob,threshold):
    actual=np.asarray(y)>0;pred=np.asarray(prob)>=threshold
    tp=int((actual&pred).sum());fp=int((~actual&pred).sum());fn=int((actual&~pred).sum())
    precision=tp/(tp+fp) if tp+fp else None;recall=tp/(tp+fn) if tp+fn else None
    f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
    return dict(positives=int(actual.sum()),predicted_positives=int(pred.sum()),tp=tp,fp=fp,fn=fn,precision=precision,recall=recall,f1=f1)

def threshold_for(y,prob):
    candidates=[.01,.025,.05,.1,.2,.35,.5]
    return max(candidates,key=lambda t:((detection(y,prob,t)['f1'] or 0),t))

def motor1(y,p,peak):
    return dict(**regression(y,p),peak=regression(y[y>=peak],p[y>=peak]),peak_threshold_kw=peak)

def motor2(y,p,c,threshold):
    a=y[:,1];b=p[:,1];active=a>.1;connected=y[:,2]>0;peak=a>=.8*max(c['evse_kw'])
    ev=detection(y[:,6],p[:,6],threshold);q=detection(y[:,5],p[:,5],.5)
    qr=np.clip(p[:,5],1e-7,1-1e-7)
    return dict(power=regression(a,b),active=regression(a[active],b[active]),connected=regression(a[connected],b[connected]),idle=regression(a[~active],b[~active]),
      detection=ev,event_threshold=threshold,peaks=int(peak.sum()),peaks_missed=int((peak&(b<.8*max(c['evse_kw']))).sum()),peak=regression(a[peak],b[peak]),
      occupancy=regression(y[:,2],p[:,2]),arrivals=regression(y[:,3],p[:,3]),queue=regression(y[:,4],p[:,4]),
      queue_risk=dict(**q,brier=float(np.mean((p[:,5]-y[:,5])**2)),logloss=float(-np.mean(y[:,5]*np.log(qr)+(1-y[:,5])*np.log(1-qr)))),
      selection_score=float(.5*((np.abs(b[active]-a[active]).mean() if active.any() else 0)+(np.abs(b[~active]-a[~active]).mean() if (~active).any() else 0))/c['ev_limit_kw']+.1*(1-(ev['f1'] or 0))),
      no_queue_positives=not bool(y[:,5].any()))

def quantile(y,q,point):
    e=y-q;upper=np.maximum(q,point);active=y>.1
    return dict(pinball=float(np.maximum(.9*e,-.1*e).mean()),raw_coverage=float((y<=q+1e-9).mean()),upper_coverage=float((y<=upper+1e-9).mean()),
      active_raw_coverage=float((y[active]<=q[active]+1e-9).mean()) if active.any() else None,
      crossing_rate=float((q<point).mean()),mean_raw_kw=float(q.mean()),mean_upper_kw=float(upper.mean()))
