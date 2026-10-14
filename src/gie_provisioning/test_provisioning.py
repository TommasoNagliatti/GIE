import copy,json,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from pydantic import ValidationError
from gie_multistation.api import create_app
from gie_multistation.registry import ROOT
from .contracts import Provision,ModelState,ModelVersion
from .examples import fixture,sample

COMM='Commercial_HighAutonomy_V2';POST='DEMO_POSTO_24H_001';HOUSE='DEMO_CASA_001';NEW='NEW_NO_HISTORY'
TOKEN='phase5-test-only-'+'x'*32;READ='phase5-read-only-'+'y'*32

class ContractTests(unittest.TestCase):
    def test_complete_baseline_without_files(self):
        c=Provision.model_validate(fixture());self.assertEqual(c.training_state,'BASELINE');self.assertEqual(len(c.energy_config().evses),5)
        self.assertEqual(Provision.model_validate(fixture('123')).station_id,'123')
    def test_paths_reserved_and_invalid_timezone(self):
        for sid in ['../bad','C:\\other','CON','com1','a/b','..']:
            with self.subTest(sid=sid),self.assertRaises(ValidationError):Provision.model_validate(dict(fixture(),station_id=sid))
        with self.assertRaises(ValidationError):Provision.model_validate(dict(fixture(),timezone='Invalid/Zone'))
        with self.assertRaises(ValidationError):Provision.model_validate(dict(fixture(),model_path='other'))
    def test_no_unapproved_personalized_initialization(self):
        for state in ['CANDIDATE','PERSONALIZED','DEGRADED']:
            with self.assertRaises(ValidationError):Provision.model_validate(dict(fixture(),training_state=state))
    def test_physical_limits_and_identity(self):
        for change in [dict(import_kw=-1),dict(export_kw=float('nan')),dict(chargers=[dict(evse_id='A',max_kw=7,minimum_kw=8)]),dict(solar=[dict(solar_id='PV',inverter_id='unknown',dc_kwp=2)])]:
            with self.assertRaises(ValidationError):Provision.model_validate(dict(fixture(),**change))
    def test_versioned_transition_contract(self):
        for state in ['BASELINE','DEGRADED']:self.assertEqual(ModelState(station_id=NEW,state=state).state,state)
        self.assertEqual(ModelState(station_id=NEW,state='CANDIDATE',candidate_version='v1').state,'CANDIDATE')
        self.assertEqual(ModelState(station_id=NEW,state='PERSONALIZED',active_version='v1').active_version,'v1')
        with self.assertRaises(ValidationError):ModelState(station_id=NEW,state='PERSONALIZED')
        base=dict(station_id=NEW,version='v1',expected_revision=0,artifact_sha256='a'*64)
        for action in ['REGISTER_CANDIDATE','ROLLBACK']:ModelVersion(action=action,**base)
        with self.assertRaises(ValidationError):ModelVersion(action='ACTIVATE',**base)
        ModelVersion(action='ACTIVATE',validation_sha256='b'*64,**base)

class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gie-provision-test-');self.addCleanup(self.temp.cleanup)
        ids=[COMM,POST,HOUSE,NEW,'NEW_BATTERY','NEW_OFFGRID','NEW_ZERO','NEW_OTHER']
        self.tokens={TOKEN:ids,READ:[NEW]};self.app=create_app(self.tokens,self.temp.name,[TOKEN])
        self.client=TestClient(self.app);self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.headers={'Authorization':'Bearer '+TOKEN}
    def post(self,path,body={},headers=None):return self.client.post(path,json=body,headers=headers or self.headers)
    def provision(self,c):
        r=self.post('/v2/stations',c);self.assertEqual(r.status_code,200,r.text)
        r=self.post('/v1/stations/'+c['station_id']+'/initialize');self.assertEqual(r.status_code,200,r.text);return r.json()
    def cycle(self,c,body):return self.post('/v2/stations/'+c['station_id']+'/cycle',body)
    def test_four_stations_real_workers_and_isolation(self):
        c=fixture();dynamic=self.provision(c)
        with ThreadPoolExecutor(3) as p:old=list(p.map(lambda sid:self.post('/v1/stations/'+sid+'/initialize').json(),[COMM,POST,HOUSE]))
        self.assertEqual(len({x['pid'] for x in old+[dynamic]}),4)
        self.assertEqual(dynamic['model_identity']['state'],'BASELINE');self.assertIsNone(dynamic['model_identity']['artifact_path'])
        missing=self.cycle(c,dict(issue_time='2026-10-13T00:00:00-04:00')).json()
        self.assertFalse(missing['state']['execution_allowed']);self.assertIsNone(missing['state']['numeric_state']['building_kw'])
        self.assertIsNone(missing['state']['visual_state']['evse_1_active'])
        self.assertEqual(missing['state']['station_extension']['operational_state'],'DEGRADED')
        self.assertTrue(all(not r['is_measurement'] and r['origin']=='ESTIMATE' for r in missing['state']['forecasts']['records']))
        dynamic=self.cycle(c,sample(c)).json();self.assertTrue(dynamic['state']['execution_allowed'],dynamic)
        self.assertEqual(len(dynamic['state']['management']['plan']),48)
        self.assertTrue(dynamic['state']['timestamp'].endswith('-04:00'))
        self.assertEqual(len(dynamic['state']['numeric_state']['evse_setpoints_kw']),5)
        with ThreadPoolExecutor(3) as p:results=list(p.map(lambda sid:self.post('/v1/stations/'+sid+'/cycle').json(),[COMM,POST,HOUSE]))
        self.assertTrue(all(r['state']['execution_allowed'] for r in results))
        evidence={'origin':'SIMULATED','transport':'FastAPI ASGI TestClient; real spawned workers','stations':[{k:r[k] for k in ['station_id','pid','generation','model_identity','hardware_commands_sent']} for r in results+[dynamic]],'new_station_result':dynamic['state']}
        (ROOT/'reports/provisioning/v1/four_stations.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        home=self.client.get('/v1/stations/'+HOUSE+'/state',headers=self.headers).json()
        proc=self.app.state.manager.slots[NEW]['process'];proc.terminate();proc.join(5)
        restored=self.post('/v1/stations/'+NEW+'/restart').json()
        self.assertEqual(restored['simulation_state'],dynamic['simulation_state'])
        self.assertNotEqual(restored['generation'],dynamic['generation'])
        self.assertEqual(self.client.get('/v1/stations/'+HOUSE+'/state',headers=self.headers).json(),home)
        self.assertEqual(self.cycle(c,sample(c)).status_code,422)
    def test_authorization_idempotency_and_immutable_technical_config(self):
        c=fixture();self.assertEqual(self.client.post('/v2/stations',json=c).status_code,401)
        self.assertEqual(self.post('/v2/stations',c,{'Authorization':'Bearer '+READ}).status_code,403)
        self.assertEqual(self.post('/v2/stations',dict(c,station_id='UNAUTHORIZED')).status_code,403)
        first=self.post('/v2/stations',c);self.assertEqual(first.status_code,200)
        self.assertEqual(self.post('/v2/stations',c).json(),first.json())
        self.assertEqual(self.post('/v2/stations',dict(c,import_kw=80)).status_code,409)
        self.assertEqual(self.client.get('/v2/stations/'+NEW+'/configuration',headers=self.headers).json(),first.json())
        req=dict(station_id=NEW,action='ACTIVATE',version='v1',expected_revision=0,artifact_sha256='a'*64,validation_sha256='b'*64)
        self.assertEqual(self.post('/v2/stations/'+NEW+'/model-transition',req).status_code,409)
    def test_missing_stale_untrusted_future_and_cross_station(self):
        c=fixture();self.provision(c)
        for change in [dict(observed_at='2026-10-12T23:00:00-04:00'),dict(available_at='2026-10-13T00:01:00-04:00'),dict(quality='UNTRUSTED')]:
            body=sample(c);body['current'].update(change);r=self.cycle(c,body)
            self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['state']['execution_allowed']);self.assertEqual(r.json()['simulation_state']['cycles'],0)
        body=sample(c);body['current']['station_id']=HOUSE
        self.assertEqual(self.cycle(c,body).status_code,422)
        body=sample(c);del body['current']['building_kw']
        self.assertEqual(self.cycle(c,body).status_code,422)
        self.assertTrue(self.cycle(c,sample(c)).json()['state']['execution_allowed'])
    def test_insufficient_grid_no_fake_service_and_retry(self):
        c=dict(fixture('NEW_OFFGRID'),import_kw=1.,baseline_building_kw=1.);self.provision(c)
        bad=self.cycle(c,sample(c,building=3)).json();self.assertFalse(bad['state']['execution_allowed']);self.assertEqual(bad['simulation_state']['cycles'],0)
        good=self.cycle(c,sample(c,building=.5)).json();self.assertTrue(good['state']['execution_allowed'])
        self.assertLessEqual(good['state']['numeric_state']['ev_served_kw'],.50002)
    def test_battery_and_inverter_failure_no_solar_persistent_soc(self):
        c=fixture('NEW_BATTERY');c.update(inverters=[dict(inverter_id='I',ac_kw=8)],batteries=[dict(battery_id='B',capacity_kwh=13,soc_initial=.7,soc_min=.2,soc_max=.9,charge_kw=3,discharge_kw=4,eta_charge=.9,eta_discharge=.92,inverter_id='I')],solar=[dict(solar_id='PV',inverter_id='I',dc_kwp=5)])
        initial=self.provision(c)['simulation_state']
        body=sample(c);body['current']['battery_available']={'B':False}
        r=self.cycle(c,body).json();self.assertTrue(r['state']['execution_allowed']);self.assertEqual(r['simulation_state']['energy_kwh'],initial['energy_kwh'])
        body=sample(c,'2026-10-13T00:15:00-04:00',solar=4);body['current']['inverter_available']={'I':False}
        r=self.cycle(c,body).json();self.assertTrue(r['state']['execution_allowed']);self.assertAlmostEqual(r['state']['management']['first_decision']['solar_used_kw'],0.)
        self.assertEqual(r['simulation_state']['energy_kwh'],initial['energy_kwh'])
    def test_service_restart_restores_dynamic_registration_and_soc(self):
        c=fixture();self.provision(c);saved=self.cycle(c,sample(c)).json()['simulation_state']
        self.client.__exit__(None,None,None)
        with TestClient(create_app(self.tokens,self.temp.name,[TOKEN])) as client:
            r=client.post('/v1/stations/'+NEW+'/initialize',json={},headers=self.headers)
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['simulation_state'],saved)
            self.assertEqual(len(client.get('/v1/stations',headers=self.headers).json()),4)
    def test_zero_equipment_and_unknown_power_not_zero_measurement(self):
        c=dict(fixture('NEW_ZERO'),chargers=[],circuits=[],baseline_building_kw=None);self.provision(c)
        r=self.cycle(c,{'issue_time':'2026-10-13T00:00:00-04:00'}).json()
        self.assertIsNone(r['state']['forecasts']['records'][0]['building_kw'])
        self.assertFalse(r['state']['execution_allowed'])
        r=self.cycle(c,sample(c,building=2)).json();self.assertTrue(r['state']['execution_allowed']);self.assertEqual(r['state']['numeric_state']['evse_setpoints_kw'],[])
    def test_concurrent_registration_and_private_directories(self):
        c=fixture()
        with ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:self.post('/v2/stations',c),range(4)))
        self.assertTrue(all(r.status_code==200 for r in results))
        self.assertEqual(len(list((Path(self.temp.name)/'configurations').glob('*.json'))),1)
        for name in ['models','history','cache']:self.assertTrue((Path(self.temp.name)/NEW/name).is_dir())
        self.assertEqual(self.post('/v1/stations/'+NEW+'/initialize').status_code,200)
        self.assertEqual(self.post('/v1/stations/'+NEW+'/mode',{'mode':'PRESENTATION'}).status_code,422)
        self.assertEqual(self.post('/v1/stations/'+NEW+'/mode',{'mode':'SIMULATION'}).status_code,200)
    def test_malformed_current_and_unregistered_configuration(self):
        c=fixture();self.provision(c)
        for changes in [dict(origin='MEASURED'),dict(battery_available={'wrong':False}),dict(inverter_available={'wrong':False}),dict(solar_kw=10)]:
            body=sample(c);body['current'].update(changes);self.assertEqual(self.cycle(c,body).status_code,422)
        self.assertEqual(self.client.get('/v2/stations/NEW_OTHER/configuration',headers=self.headers).status_code,404)

if __name__=='__main__':unittest.main(verbosity=2)
