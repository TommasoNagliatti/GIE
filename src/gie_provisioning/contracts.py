"""Strict technical contracts; all paths remain server-owned."""
import re
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from gie_energy_v3.config import Config, Battery, Inverter, EVSE, Circuit

def station_id(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',value) or value.upper() in {'CON','PRN','AUX','NUL',*[f'{p}{i}' for p in ('COM','LPT') for i in range(1,10)]}:
        raise ValueError('Invalid station identity')
    return value

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class Charger(Strict):
    evse_id:str=Field(min_length=1,max_length=64)
    max_kw:float=Field(gt=0,le=1000)
    minimum_kw:float=Field(default=0,ge=0)
    available:bool=True
class Storage(Strict):
    battery_id:str=Field(min_length=1,max_length=64)
    capacity_kwh:float=Field(gt=0,le=100000)
    soc_initial:float=Field(ge=0,le=1)
    soc_min:float=Field(ge=0,le=1)
    soc_max:float=Field(ge=0,le=1)
    charge_kw:float=Field(ge=0,le=10000)
    discharge_kw:float=Field(ge=0,le=10000)
    eta_charge:float=Field(gt=0,le=1)
    eta_discharge:float=Field(gt=0,le=1)
    inverter_id:str
    available:bool=True
class Converter(Strict):
    inverter_id:str=Field(min_length=1,max_length=64)
    ac_kw:float=Field(gt=0,le=10000)
    available:bool=True
class Solar(Strict):
    solar_id:str=Field(min_length=1,max_length=64)
    inverter_id:str
    dc_kwp:float=Field(gt=0,le=10000)
    available:bool=True
class Branch(Strict):
    circuit_id:str=Field(min_length=1,max_length=64)
    evse_ids:list[str]=Field(min_length=1,max_length=64)
    max_kw:float=Field(ge=0,le=10000)

class Provision(Strict):
    schema_version:Literal['1.0']='1.0'
    station_id:str
    timezone:str
    import_kw:float=Field(ge=0,le=100000)
    export_kw:float=Field(ge=0,le=100000)
    chargers:list[Charger]=Field(max_length=64)
    batteries:list[Storage]=Field(max_length=16)
    solar:list[Solar]=Field(max_length=32)
    inverters:list[Converter]=Field(max_length=32)
    circuits:list[Branch]=Field(default_factory=list,max_length=64)
    policy:Literal['solar_only_lex_v3.0','grid_allowed_lex_v3.0']='solar_only_lex_v3.0'
    training_state:Literal['BASELINE']='BASELINE'
    baseline_building_kw:float|None=Field(default=None,ge=0,le=100000)
    origin:Literal['SIMULATED']='SIMULATED'
    @field_validator('station_id')
    @classmethod
    def identity(cls,value):return station_id(value)
    @field_validator('timezone')
    @classmethod
    def timezone_valid(cls,value):
        try:ZoneInfo(value)
        except Exception as e:raise ValueError('IANA timezone required') from e
        return value
    def energy_config(self):
        solar={i.inverter_id:sum(s.dc_kwp for s in self.solar if s.inverter_id==i.inverter_id and s.available) for i in self.inverters}
        return Config(self.station_id,self.import_kw,self.export_kw,
            batteries=[Battery(**b.model_dump()) for b in self.batteries],
            inverters=[Inverter(**i.model_dump(),pv_dc_kwp=solar[i.inverter_id]) for i in self.inverters],
            evses=[EVSE(**v.model_dump()) for v in self.chargers],
            circuits=[Circuit(**c.model_dump()) for c in self.circuits],policy=self.policy).validate()
    @model_validator(mode='after')
    def physical(self):
        if len({s.solar_id for s in self.solar})!=len(self.solar) or any(s.inverter_id not in {i.inverter_id for i in self.inverters} for s in self.solar):raise ValueError('Invalid solar identity/inverter')
        self.energy_config()
        return self
    def worker_config(self):
        return dict(station_id=self.station_id,kind='baseline',profile='dynamic_baseline_v1',timezone=self.timezone,
            technical=self.model_dump(),default_issue=None,origin='SIMULATED',physical_dispatch=False)

class Request(Strict):
    evse_id:str
    connected:bool
    requested_kw:float=Field(ge=0)
    available:bool=True
    vehicle_max_kw:float|None=Field(default=None,ge=0)
class Sample(Strict):
    station_id:str
    observed_at:str
    available_at:str
    origin:Literal['SIMULATED']
    quality:Literal['TRUSTED','UNTRUSTED']
    building_kw:float=Field(ge=0)
    solar_kw:float=Field(ge=0)
    demands:list[Request]=Field(max_length=64)
    battery_available:dict[str,bool]=Field(default_factory=dict)
    inverter_available:dict[str,bool]=Field(default_factory=dict)
    grid_available:bool=True
class DynamicCycle(Strict):
    issue_time:str
    current:Sample|None=None

class ModelVersion(Strict):
    """Future activation request only; no arbitrary artifact path or code upload."""
    contract_version:Literal['1.0']='1.0'
    station_id:str
    action:Literal['REGISTER_CANDIDATE','ACTIVATE','ROLLBACK']
    version:str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    expected_revision:int=Field(ge=0)
    artifact_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    validation_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    @model_validator(mode='after')
    def approval(self):
        station_id(self.station_id)
        if self.action=='ACTIVATE' and self.validation_sha256 is None:raise ValueError('Activation requires approved validation evidence')
        return self

class ModelState(Strict):
    schema_version:Literal['1.0']='1.0'
    station_id:str
    state:Literal['BASELINE','CANDIDATE','PERSONALIZED','DEGRADED']='BASELINE'
    revision:int=Field(default=0,ge=0)
    active_version:str|None=None
    candidate_version:str|None=None
    previous_version:str|None=None
    activation_supported:Literal[False]=False
    @model_validator(mode='after')
    def identities(self):
        station_id(self.station_id)
        if self.state=='PERSONALIZED' and not self.active_version:raise ValueError('Personalized requires active station version')
        if self.state=='CANDIDATE' and not self.candidate_version:raise ValueError('Candidate requires station version')
        return self
