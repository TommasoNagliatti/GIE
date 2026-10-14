"""New MILP, independent of frozen MPC. AC kW and individual stored kWh."""
from time import perf_counter
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from scipy.sparse import coo_matrix
from .guard import verify
N=48;DT=.25;TOL=2e-5;LEX_TOL=1e-5

class Problem:
    def __init__(self):self.lo=[];self.hi=[];self.integer=[];self.rows=[];self.lower=[];self.upper=[]
    def vars(self,shape,lo=0.,hi=np.inf,binary=False):
        n=int(np.prod(shape));a=np.arange(len(self.lo),len(self.lo)+n).reshape(shape)
        self.lo.extend(np.broadcast_to(lo,shape).ravel());self.hi.extend(np.broadcast_to(hi,shape).ravel());self.integer.extend([int(binary)]*n);return a
    def row(self,terms,lo=-np.inf,hi=np.inf):self.rows.append(terms);self.lower.append(lo);self.upper.append(hi)
    def solve(self,c,seconds):
        rr=[];cc=[];dd=[]
        for i,r in enumerate(self.rows):
            for j,v in r.items():rr.append(i);cc.append(j);dd.append(v)
        a=coo_matrix((dd,(rr,cc)),shape=(len(self.rows),len(self.lo))).tocsc()
        return milp(c,integrality=np.array(self.integer),bounds=Bounds(self.lo,self.hi),constraints=LinearConstraint(a,self.lower,self.upper),options={'time_limit':seconds,'mip_rel_gap':1e-8})

def inputs(c,energy,building,pv,demand):
    c.validate();building=np.asarray(building,dtype=float);pv=np.asarray(pv,dtype=float);demand=np.asarray(demand,dtype=float)
    if building.shape!=(N,) or pv.shape!=(N,len(c.inverters)) or demand.shape!=(N,len(c.evses)):raise ValueError('48-step input shapes required')
    if any(not np.isfinite(a).all() or (a<0).any() for a in [building,pv,demand]):raise ValueError('Nonfinite or negative inputs')
    if set(energy)!={b.battery_id for b in c.batteries}:raise ValueError('Individual energy identities mismatch')
    for b in c.batteries:
        v=energy[b.battery_id]
        if not np.isfinite(v) or not b.soc_min*b.capacity_kwh-1e-7<=v<=b.soc_max*b.capacity_kwh+1e-7:raise ValueError('Initial SOC outside bounds')
    for j,v in enumerate(c.inverters):
        if (pv[:,j]>v.pv_dc_kwp+1e-7).any():raise ValueError('PV exceeds configured source rating')
    caps=np.array([v.max_kw if v.available else 0. for v in c.evses])
    return building,pv,np.minimum(demand,caps)

def optimize(c,energy,building,pv,demand):
    started=perf_counter()
    try:
        building,pv,caps=inputs(c,energy,building,pv,demand)
        nb=len(c.batteries);ni=len(c.inverters);ne=len(c.evses);p=Problem()
        imp=p.vars((N,),hi=c.import_kw);exp=p.vars((N,),hi=c.export_kw)
        used=p.vars((N,ni),hi=pv);ev=p.vars((N,ne),hi=caps)
        charge=p.vars((N,nb));discharge=p.vars((N,nb))
        energies=p.vars((N,nb),lo=[b.soc_min*b.capacity_kwh for b in c.batteries],hi=[b.soc_max*b.capacity_kwh for b in c.batteries])
        grid_mode=p.vars((N,),hi=1,binary=True)
        battery_mode=p.vars((N,),hi=1,binary=True) if nb else None
        admission={j:p.vars((N,),hi=1,binary=True) for j,e in enumerate(c.evses) if e.minimum_kw>0}
        inv={v.inverter_id:j for j,v in enumerate(c.inverters)}
        for t in range(N):
            balance={imp[t]:1,exp[t]:-1}
            balance.update({x:1 for x in used[t]});balance.update({x:-1 for x in ev[t]});balance.update({x:-1 for x in charge[t]});balance.update({x:1 for x in discharge[t]})
            p.row(balance,building[t],building[t])
            p.row({imp[t]:1,grid_mode[t]:-c.import_kw},hi=0)
            p.row({exp[t]:1,grid_mode[t]:c.export_kw},hi=c.export_kw)
            for j,b in enumerate(c.batteries):
                available=b.available and c.inverters[inv[b.inverter_id]].available
                capc=b.charge_kw if available else 0.;capd=b.discharge_kw if available else 0.
                p.row({charge[t,j]:1,battery_mode[t]:-capc},hi=0)
                p.row({discharge[t,j]:1,battery_mode[t]:capd},hi=capd)
                terms={energies[t,j]:1,charge[t,j]:-DT*b.eta_charge,discharge[t,j]:DT/b.eta_discharge}
                if t:terms[energies[t-1,j]]=-1
                rhs=energy[b.battery_id] if t==0 else 0.
                p.row(terms,rhs,rhs)
            if nb:
                # Discharge serves local load only; never export stored energy.
                terms={x:1 for x in discharge[t]};terms.update({x:-1 for x in ev[t]});p.row(terms,hi=building[t])
                if c.policy=='solar_only_lex_v3.0':p.row({imp[t]:1,battery_mode[t]:c.import_kw},hi=c.import_kw)
            for j,v in enumerate(c.inverters):
                terms={used[t,j]:1}
                for k,b in enumerate(c.batteries):
                    if b.inverter_id==v.inverter_id:terms[charge[t,k]]=1;terms[discharge[t,k]]=1
                p.row(terms,hi=v.ac_kw if v.available else 0.)
            for j,z in admission.items():
                p.row({ev[t,j]:1,z[t]:-caps[t,j]},hi=0)
                p.row({ev[t,j]:-1,z[t]:c.evses[j].minimum_kw},hi=0)
            for circuit in c.circuits:
                p.row({ev[t,j]:1 for j,v in enumerate(c.evses) if v.evse_id in circuit.evse_ids},hi=circuit.max_kw)
        objectives=[]
        def objective(name,idx,coefficient):
            cost=np.zeros(len(p.lo));cost[np.asarray(idx).ravel()]=coefficient;objectives.append((name,cost))
        if ne:objective('maximize_ev_12h',ev,-DT);objective('maximize_ev_now',ev[0],-DT)
        objective('minimize_import',imp,DT);objective('minimize_import_now',imp[:1],DT);objective('minimize_curtailment',used,-DT)
        objective('minimize_throughput',np.concatenate([charge.ravel(),discharge.ravel(),imp,exp]),DT)
        stages=[];result=None
        for name,cost in objectives:
            result=p.solve(cost,c.solver_seconds)
            stages.append(dict(stage=name,status=int(result.status),message=result.message))
            if result.status!=0 or result.x is None:
                return dict(status='infeasible' if result.status==2 else 'solver_failed',execution_allowed=False,policy=c.policy,diagnostic=result.message,stages=stages,physical_dispatch=False)
            optimum=float(cost@result.x);stages[-1]['objective']=optimum
            p.row({i:float(v) for i,v in enumerate(cost) if v},hi=optimum+LEX_TOL)
        x=result.x;plan=[]
        for t in range(N):
            row=dict(step=t,building_kw=float(building[t]),solar_available_kw=float(pv[t].sum()),solar_used_kw=float(x[used[t]].sum()),solar_curtailed_kw=float(pv[t].sum()-x[used[t]].sum()),
                grid_import_kw=float(x[imp[t]]),grid_export_kw=float(x[exp[t]]),ev_requested_kw=float(np.asarray(demand)[t].sum()),ev_served_kw=float(x[ev[t]].sum()),
                evse_setpoints_kw={v.evse_id:float(x[ev[t,j]]) for j,v in enumerate(c.evses)},
                solar_by_inverter_kw={v.inverter_id:float(x[used[t,j]]) for j,v in enumerate(c.inverters)},
                batteries={b.battery_id:dict(charge_kw=float(x[charge[t,j]]),discharge_kw=float(x[discharge[t,j]]),energy_after_kwh=float(x[energies[t,j]]),soc_after=float(x[energies[t,j]]/b.capacity_kwh)) for j,b in enumerate(c.batteries)})
            plan.append(row)
        verification=verify(c,energy,building,pv,caps,plan)
        return dict(status='optimal',execution_allowed=True,policy=c.policy,plan=plan,first_decision=plan[0],stages=stages,verification=verification,elapsed_ms=(perf_counter()-started)*1000,physical_dispatch=False,hardware_commands_sent=False)
    except (ValueError,AssertionError) as exc:
        return dict(status='blocked',execution_allowed=False,policy=c.policy,diagnostic=str(exc),physical_dispatch=False,hardware_commands_sent=False)
