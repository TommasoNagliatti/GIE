"""Explicit AC-side physical configuration. No commercial defaults."""
from dataclasses import dataclass,field,asdict
import hashlib,json,math

@dataclass
class Battery:
    battery_id:str
    capacity_kwh:float
    soc_initial:float
    soc_min:float
    soc_max:float
    charge_kw:float
    discharge_kw:float
    eta_charge:float
    eta_discharge:float
    inverter_id:str
    available:bool=True
@dataclass
class Inverter:
    inverter_id:str
    ac_kw:float
    pv_dc_kwp:float=0.
    available:bool=True
@dataclass
class EVSE:
    evse_id:str
    max_kw:float
    minimum_kw:float=0.
    available:bool=True
@dataclass
class Circuit:
    circuit_id:str
    evse_ids:list[str]
    max_kw:float
@dataclass
class Config:
    station_id:str
    import_kw:float
    export_kw:float
    batteries:list[Battery]=field(default_factory=list)
    inverters:list[Inverter]=field(default_factory=list)
    evses:list[EVSE]=field(default_factory=list)
    circuits:list[Circuit]=field(default_factory=list)
    policy:str='solar_only_lex_v3.0'
    solver_seconds:float=10.
    def validate(self):
        def finite(*vals):
            if any(not math.isfinite(v) or v<0 for v in vals):raise ValueError('Invalid physical configuration')
        finite(self.import_kw,self.export_kw,self.solver_seconds)
        if self.policy not in ('solar_only_lex_v3.0','grid_allowed_lex_v3.0') or self.solver_seconds<=0:raise ValueError('Invalid policy/solver time')
        for seq,key in [(self.batteries,'battery_id'),(self.inverters,'inverter_id'),(self.evses,'evse_id'),(self.circuits,'circuit_id')]:
            ids=[getattr(x,key) for x in seq]
            if len(set(ids))!=len(ids) or any(not x for x in ids):raise ValueError('Duplicate or empty equipment identity')
        inv={i.inverter_id for i in self.inverters};ev={e.evse_id for e in self.evses}
        for i in self.inverters:
            finite(i.ac_kw,i.pv_dc_kwp)
            if i.ac_kw<=0 or type(i.available) is not bool:raise ValueError('Invalid inverter')
        for b in self.batteries:
            finite(b.capacity_kwh,b.charge_kw,b.discharge_kw,b.eta_charge,b.eta_discharge,b.soc_min,b.soc_max,b.soc_initial)
            if not 0<=b.soc_min<=b.soc_initial<=b.soc_max<=1 or b.soc_min==b.soc_max or b.capacity_kwh<=0 or not 0<b.eta_charge<=1 or not 0<b.eta_discharge<=1 or b.inverter_id not in inv or type(b.available) is not bool:raise ValueError('Invalid battery')
        for e in self.evses:
            finite(e.max_kw,e.minimum_kw)
            if e.max_kw<=0 or e.minimum_kw>e.max_kw or type(e.available) is not bool:raise ValueError('Invalid EVSE')
        for c in self.circuits:
            finite(c.max_kw)
            if not c.evse_ids or len(c.evse_ids)!=len(set(c.evse_ids)) or set(c.evse_ids)-ev:raise ValueError('Invalid circuit members')
        return self
    def fingerprint(self):return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()
    def initial_energy(self):return {b.battery_id:b.capacity_kwh*b.soc_initial for b in self.batteries}

def from_manifest(manifest):
    e=manifest['equipment']
    c=Config(manifest['station_id'],e['grid']['import_kw'],e['grid']['export_kw'])
    c.inverters=[Inverter(i['id'],i['ac_kw'],i['pv_dc_kwp']) for i in e['inverters']]
    c.batteries=[Battery(b['id'],b['nominal_kwh'],b['soc_initial'],b['soc_min'],b['soc_max'],b['charge_kw'],b['discharge_kw'],b['eta_charge'],b['eta_discharge'],b['inverter_id']) for b in e['batteries']]
    c.evses=[EVSE(v['id'],v['max_kw']) for v in e['evse']]
    return c.validate()
