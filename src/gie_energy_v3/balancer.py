"""Variable EVSE max-min allocation; setpoints are limits, not meter readings."""
import numpy as np
from scipy.optimize import linprog
from .mpc import Problem

def allocate(evses,requests,budget,circuits=(),cycle=0):
    if not np.isfinite(budget) or budget<0:raise ValueError('Invalid EV budget')
    if set(requests)!={e.evse_id for e in evses}:raise ValueError('EVSE identity mismatch')
    caps=[]
    for e in evses:
        d=requests[e.evse_id]
        if type(d.get('connected')) is not bool or type(d.get('available',True)) is not bool:raise ValueError('Invalid availability')
        values=[d['requested_kw'],d.get('vehicle_max_kw',e.max_kw)]
        if any(not np.isfinite(v) or v<0 for v in values):raise ValueError('Invalid requested/vehicle power')
        caps.append(min(*values,e.max_kw) if e.available and d['connected'] and d.get('available',True) else 0.)
    n=len(evses)
    if not n:return {'setpoints_kw':{},'allocated_kw':0.,'suspended':[]}
    p=Problem();x=p.vars((n,),hi=caps);binary={}
    for j,e in enumerate(evses):
        if e.minimum_kw>0:
            z=int(p.vars((1,),hi=1,binary=True)[0]);binary[j]=z
            p.row({x[j]:1,z:-caps[j]},hi=0);p.row({x[j]:-1,z:e.minimum_kw},hi=0)
    p.row({i:1 for i in x},hi=budget)
    groups=[]
    for c in circuits:
        a=np.array([float(e.evse_id in c.evse_ids) for e in evses]);groups.append((a,c.max_kw));p.row({x[j]:1 for j in range(n) if a[j]},hi=c.max_kw)
    cost=np.zeros(len(p.lo));cost[x]=-1;r=p.solve(cost,5.)
    if r.status!=0:raise ValueError('Load balancer infeasible')
    target=float(r.x[x].sum())
    # Rotate preference only among equally optimal admission sets.
    if binary:
        p.row({i:1 for i in x},lo=target-1e-7)
        cost=np.zeros(len(p.lo))
        for j,z in binary.items():cost[z]=-float(n-((j-cycle)%n))
        r=p.solve(cost,5.)
        if r.status!=0:raise ValueError('Admission tie-break failed')
    admitted=[j for j in range(n) if caps[j]>0 and (j not in binary or r.x[binary[j]]>.5)]
    bounds=[(e.minimum_kw if j in admitted else 0.,caps[j] if j in admitted else 0.) for j,e in enumerate(evses)]
    # Lexicographic max-min via successive water levels, preserving feasible total.
    fixed={};free=set(admitted);values=np.zeros(n)
    while free:
        aub=[];bub=[]
        for a,b in groups:aub.append(np.r_[a,0.]);bub.append(b)
        for j in free:
            a=np.zeros(n+1);a[j]=-1;a[-1]=1;aub.append(a);bub.append(0.)
        eq=[np.r_[np.ones(n),0.]];rhs=[target]
        for j,v in fixed.items():a=np.zeros(n+1);a[j]=1;eq.append(a);rhs.append(v)
        result=linprog(np.r_[np.zeros(n),-1.],A_ub=np.array(aub) if aub else None,b_ub=bub or None,A_eq=eq,b_eq=rhs,bounds=bounds+[(0,None)],method='highs')
        if not result.success:raise ValueError('Fair allocation infeasible')
        values=result.x[:n];level=result.x[-1];forced=[]
        for j in free:
            if values[j]>level+1e-7:continue
            objective=np.zeros(n+1);objective[j]=-1
            test=linprog(objective,A_ub=np.array(aub),b_ub=bub,A_eq=eq,b_eq=rhs,bounds=bounds+[(level,None)],method='highs')
            if test.success and test.x[j]<=level+1e-7:forced.append(j)
        if not forced:raise ValueError('Cannot identify fair bottleneck')
        for j in forced:fixed[j]=float(values[j]);free.remove(j)
    if not admitted:values=np.zeros(n)
    for j,e in enumerate(evses):
        if values[j]<-1e-6 or values[j]>caps[j]+1e-6 or 1e-6<values[j]<e.minimum_kw-1e-6:raise ValueError('Unsafe allocation')
    if values.sum()>budget+1e-6:raise ValueError('Budget exceeded')
    return {'setpoints_kw':{e.evse_id:float(max(0,values[j])) for j,e in enumerate(evses)},'allocated_kw':float(values.sum()),'suspended':[e.evse_id for j,e in enumerate(evses) if caps[j]>0 and values[j]<1e-6]}
