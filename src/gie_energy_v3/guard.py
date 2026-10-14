"""Independent numerical acceptance guard; no optimizer variables reused."""
import math

def verify(c,initial,building,pv,caps,plan,tolerance=2e-5):
    if len(plan)!=48:raise ValueError('Incomplete horizon')
    energy=dict(initial);max_balance=0.;max_energy=0.;active=set()
    def within(value,lo,hi,label):
        if not math.isfinite(value) or value<lo-tolerance or value>hi+tolerance:raise ValueError('Physical guard: '+label)
    for t,r in enumerate(plan):
        gi=r['grid_import_kw'];ge=r['grid_export_kw']
        within(gi,0,c.import_kw,'import');within(ge,0,c.export_kw,'export')
        if gi>tolerance and ge>tolerance:raise ValueError('Simultaneous import/export')
        if abs(gi-c.import_kw)<tolerance:active.add('grid_import_limit')
        if abs(ge-c.export_kw)<tolerance:active.add('grid_export_limit')
        totalc=totald=0.
        for b in c.batteries:
            q=r['batteries'][b.battery_id];inv=next(i for i in c.inverters if i.inverter_id==b.inverter_id)
            avail=b.available and inv.available;cc=q['charge_kw'];dd=q['discharge_kw']
            within(cc,0,b.charge_kw if avail else 0,'battery charge');within(dd,0,b.discharge_kw if avail else 0,'battery discharge')
            expected=energy[b.battery_id]+.25*(b.eta_charge*cc-dd/b.eta_discharge)
            err=abs(expected-q['energy_after_kwh']);max_energy=max(max_energy,err)
            if err>tolerance:raise ValueError('Individual energy conservation')
            within(q['energy_after_kwh'],b.capacity_kwh*b.soc_min,b.capacity_kwh*b.soc_max,'SOC')
            if abs(q['soc_after']-q['energy_after_kwh']/b.capacity_kwh)>tolerance:raise ValueError('SOC display mismatch')
            if abs(q['soc_after']-b.soc_min)<tolerance:active.add(b.battery_id+':soc_min')
            if abs(q['soc_after']-b.soc_max)<tolerance:active.add(b.battery_id+':soc_max')
            energy[b.battery_id]=q['energy_after_kwh'];totalc+=cc;totald+=dd
        if totalc>tolerance and totald>tolerance:raise ValueError('Contradictory battery flows')
        if c.policy=='solar_only_lex_v3.0' and totalc>tolerance and gi>tolerance:raise ValueError('Grid battery charging forbidden')
        ev=sum(r['evse_setpoints_kw'].values())
        for j,e in enumerate(c.evses):
            v=r['evse_setpoints_kw'][e.evse_id];within(v,0,caps[t,j],'EVSE cap')
            if tolerance<v<e.minimum_kw-tolerance:raise ValueError('EVSE below minimum')
        for circ in c.circuits:within(sum(r['evse_setpoints_kw'][i] for i in circ.evse_ids),0,circ.max_kw,'circuit')
        for j,inv in enumerate(c.inverters):
            used=r['solar_by_inverter_kw'][inv.inverter_id];within(used,0,pv[t,j],'PV available')
            shared=used+sum(r['batteries'][b.battery_id]['charge_kw']+r['batteries'][b.battery_id]['discharge_kw'] for b in c.batteries if b.inverter_id==inv.inverter_id)
            within(shared,0,inv.ac_kw if inv.available else 0,'shared inverter')
            if abs(shared-inv.ac_kw)<tolerance:active.add(inv.inverter_id+':ac_limit')
        if totald>building[t]+ev+tolerance:raise ValueError('Battery export forbidden')
        used=sum(r['solar_by_inverter_kw'].values());balance=used+gi+totald-building[t]-ev-totalc-ge
        max_balance=max(max_balance,abs(balance))
        if abs(balance)>tolerance:raise ValueError('AC power conservation')
        if abs(r['solar_curtailed_kw']-(sum(pv[t])-used))>tolerance:raise ValueError('Solar conservation')
        if abs(r['ev_served_kw']-ev)>tolerance:raise ValueError('EV total mismatch')
        r['balance_error_kw']=float(balance)
    return dict(max_balance_error_kw=max_balance,max_energy_error_kwh=max_energy,active_constraints=sorted(active),checked_steps=48)
