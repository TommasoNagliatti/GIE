"""Versioned service API; station identity is path + server-side token scope."""
from contextlib import asynccontextmanager
import hashlib
import json
import os
import secrets
from typing import Literal
from fastapi import FastAPI,Depends,Header,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .manager import Manager,StationError
from .registry import ROOT,registry

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Demand(Strict):
    evse_id:str
    requested_kw:float=Field(ge=0)
    connected:bool
    available:bool=True
    vehicle_max_kw:float|None=Field(default=None,ge=0)
class Current(Strict):
    building_kw:float=Field(ge=0)
    solar_kw:float=Field(ge=0)
    demands:list[Demand]=Field(max_length=4)
class Cycle(Strict):
    issue_time:str|None=None
    current:Current|None=None
class Mode(Strict):
    mode:Literal['NORMAL','SIMULATION','PRESENTATION','MANUAL_DEMO']
class Presentation(Strict):
    action:Literal['start','pause','resume','stop','reset','next','previous','scene','interval','loop']
    scene_id:str|None=None
    seconds:Literal[5,10,15]|None=None
    enabled:bool|None=None
    @model_validator(mode='after')
    def required(self):
        for action,key in [('scene','scene_id'),('interval','seconds'),('loop','enabled')]:
            if self.action==action and getattr(self,key) is None:raise ValueError(key+' required')
        return self
class Event(Strict):
    event:str
class Empty(Strict):pass

def create_app(tokens=None,data_dir=None,provisioning_tokens=None,panel_dir=None):
    # Environment JSON: {"secret-token-at-least-24-chars": ["authorized-station-id", ...]}.
    # No implicit wildcard. No raw tokens in files/logs/responses.
    scopes=tokens if tokens is not None else json.loads(os.environ.get('GIE_MULTISTATION_TOKENS','{}'))
    from gie_provisioning.contracts import station_id as validate_id,Provision,DynamicCycle,ModelVersion
    configs=registry()
    if not scopes or any(len(k)<24 or not isinstance(v,list) or not v for k,v in scopes.items()):
        raise RuntimeError('Configure service tokens of 24+ characters with explicit station scopes')
    for ids in scopes.values():
        for sid in ids:validate_id(sid)
    creators=provisioning_tokens if provisioning_tokens is not None else json.loads(os.environ.get('GIE_PROVISIONING_TOKENS','[]'))
    if not isinstance(creators,list) or set(creators)-set(scopes):raise RuntimeError('Provisioning tokens must be explicit configured service credentials')
    creator_keys={hashlib.sha256(k.encode()).digest() for k in creators}
    credentials=[(hashlib.sha256(k.encode()).digest(),frozenset(v)) for k,v in scopes.items()]
    @asynccontextmanager
    async def lifespan(app):
        app.state.manager=Manager(data_dir or os.environ.get('GIE_MULTISTATION_DATA_DIR') or ROOT/'reports/multistation/v1/runtime')
        try:
            if panel_dir:
                from gie_panel.service import PanelService
                app.state.panel=PanelService(app.state.manager,panel_dir)
            yield
        finally:
            if getattr(app.state,'panel',None):app.state.panel.close()
            app.state.manager.close()
    app=FastAPI(title='GIE Multiestação — local simulated v1',version='1.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    def authenticate(authorization:str|None=Header(default=None)):
        if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Service authentication required')
        candidate=hashlib.sha256(authorization[7:].encode()).digest()
        for key,allowed in credentials:
            if secrets.compare_digest(candidate,key):return allowed
        raise HTTPException(401,'Service authentication required')
    def authorize(station_id:str,allowed=Depends(authenticate)):
        if station_id not in allowed:raise HTTPException(403,'Station outside authorized scope')
        return station_id
    def provision_authority(authorization:str|None=Header(default=None),allowed=Depends(authenticate)):
        if hashlib.sha256(authorization[7:].encode()).digest() not in creator_keys:raise HTTPException(403,'Provisioning capability required')
        return allowed
    def call(sid,op,body=None):
        try:
            m=app.state.manager
            if op in ('start','stop','restart','health'):return getattr(m,op)(sid)
            return m.request(sid,op,body)
        except StationError as e:raise HTTPException(e.status,str(e)) from e
    @app.get('/v1/health')
    def health(allowed=Depends(authenticate)):
        return dict(status='ok',origin='SIMULATED',physical_dispatch=False,stations=[call(s,'health') for s in sorted(allowed) if s in app.state.manager.configs])
    @app.get('/v1/stations')
    def stations(allowed=Depends(authenticate)):
        return [dict(config=app.state.manager.configs[s],health=call(s,'health')) for s in sorted(allowed) if s in app.state.manager.configs]
    @app.post('/v2/stations')
    def provision(body:Provision,allowed=Depends(provision_authority)):
        if body.station_id not in allowed:raise HTTPException(403,'Station outside authorized scope')
        try:return app.state.manager.provision(body.model_dump())
        except StationError as e:raise HTTPException(e.status,str(e)) from e
    @app.get('/v2/stations/{station_id}/configuration')
    def configuration(sid=Depends(authorize)):
        try:app.state.manager.slot(sid)
        except StationError as e:raise HTTPException(e.status,str(e)) from e
        return app.state.manager.configs[sid]
    @app.post('/v2/stations/{station_id}/cycle')
    def baseline_cycle(body:DynamicCycle,sid=Depends(authorize)):
        if app.state.manager.configs.get(sid,{}).get('kind')!='baseline':raise HTTPException(409,'Dynamic cycle requires a baseline station')
        return call(sid,'cycle',body.model_dump(exclude_none=True))
    @app.post('/v2/stations/{station_id}/model-transition')
    def model_transition(body:ModelVersion,sid=Depends(authorize),allowed=Depends(provision_authority)):
        if body.station_id!=sid:raise HTTPException(422,'Model station mismatch')
        call(sid,'health')
        raise HTTPException(409,'Contract prepared only: trusted artifact validation/activation adapter not implemented; baseline remains active')
    @app.get('/v1/stations/{station_id}/health')
    def station_health(sid=Depends(authorize)):return call(sid,'health')
    @app.get('/v1/stations/{station_id}/state')
    def state(sid=Depends(authorize)):return call(sid,'state')
    @app.post('/v1/stations/{station_id}/initialize')
    def start(body:Empty,sid=Depends(authorize)):return call(sid,'start')
    @app.post('/v1/stations/{station_id}/stop')
    def stop(body:Empty,sid=Depends(authorize)):return call(sid,'stop')
    @app.post('/v1/stations/{station_id}/restart')
    def restart(body:Empty,sid=Depends(authorize)):return call(sid,'restart')
    @app.post('/v1/stations/{station_id}/cycle')
    def cycle(body:Cycle,sid=Depends(authorize)):return call(sid,'cycle',body.model_dump(exclude_none=True,exclude_unset=True))
    @app.post('/v1/stations/{station_id}/mode')
    def mode(body:Mode,sid=Depends(authorize)):return call(sid,'mode',body.model_dump())
    @app.post('/v1/stations/{station_id}/presentation')
    def presentation(body:Presentation,sid=Depends(authorize)):return call(sid,'presentation',body.model_dump())
    @app.post('/v1/stations/{station_id}/manual-demo/event')
    def manual(body:Event,sid=Depends(authorize)):return call(sid,'manual',body.model_dump())
    if panel_dir:
        from gie_panel.service import install
        install(app,authorize)
    return app
