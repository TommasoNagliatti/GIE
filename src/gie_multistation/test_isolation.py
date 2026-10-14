"""Integration tests use real spawned processes and saved models, not mocked workers."""
import concurrent.futures as cf
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from .api import create_app
from .manager import Manager
from .registry import ROOT

COMM='Commercial_HighAutonomy_V2';HOUSE='DEMO_CASA_001';POST='DEMO_POSTO_24H_001'
ADMIN='test-admin-'+('a'*32);HOME='test-house-'+('b'*32)

class IsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='gie-isolation-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.app=create_app({ADMIN:[COMM,HOUSE,POST],HOME:[HOUSE]},cls.temp.name)
        cls.client=TestClient(cls.app);cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__,None,None,None)
        cls.headers={'Authorization':'Bearer '+ADMIN}
        def start(s):
            r=cls.client.post('/v1/stations/'+s+'/initialize',headers=cls.headers,json={})
            if r.status_code!=200:raise RuntimeError(r.text)
            return r.json()
        with cf.ThreadPoolExecutor(3) as pool:cls.initial=dict(zip([COMM,HOUSE,POST],pool.map(start,[COMM,HOUSE,POST])))
    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None,None,None);cls.temp.cleanup()
    def get(self,s):return self.client.get('/v1/stations/'+s+'/state',headers=self.headers).json()
    def post(self,s,op,body={}):return self.client.post('/v1/stations/'+s+'/'+op,headers=self.headers,json=body)
    def test_01_three_real_independent_processes_models(self):
        self.assertEqual(len({s['pid'] for s in self.initial.values()}),3)
        for sid,s in self.initial.items():
            self.assertEqual(s['model_identity']['station_id'],sid);self.assertEqual(s['mode'],'NORMAL')
            self.assertIsNone(s['state'])
    def test_02_authorization_identity(self):
        self.assertEqual(self.client.get('/v1/stations').status_code,401)
        h={'Authorization':'Bearer '+HOME}
        self.assertEqual(len(self.client.get('/v1/stations',headers=h).json()),1)
        self.assertEqual(self.client.post('/v1/stations/'+POST+'/restart',headers=h,json={}).status_code,403)
        for path in ['cycle','initialize','restart','mode']:
            body={'station_id':POST}
            if path=='mode':body['mode']='SIMULATION'
            self.assertEqual(self.post(HOUSE,path,body).status_code,422)
        self.assertEqual(self.post('unknown','initialize').status_code,403)
    def test_03_concurrent_real_cycles_contract(self):
        with cf.ThreadPoolExecutor(3) as pool:r=list(pool.map(lambda s:self.post(s,'cycle'),[COMM,HOUSE,POST]))
        for sid,res in zip([COMM,HOUSE,POST],r):
            self.assertEqual(res.status_code,200,res.text);s=res.json();out=s['state']
            self.assertIn('numeric_state',out);self.assertIn('visual_state',out)
            self.assertFalse(s['hardware_commands_sent']);self.assertEqual(len(s['history']),1)
            self.assertEqual(s['history'][0]['station_id'],sid)
            self.assertEqual(out['provenance']['origin'],'SIMULATED')
            self.assertEqual(len(out['forecasts']['records']),48)
            if sid!=COMM:
                self.assertTrue(out['execution_allowed'],str(out['management']));self.assertEqual(out['status'],'optimal_simulated')
                self.assertFalse(out['visual_state']['commands_valid'])
                self.assertEqual(len(out['management']['plan']),48)
            else:self.assertTrue(out['execution_allowed'],str(out.get('health')))
    def test_04_modes_independent(self):
        before=self.get(POST)
        self.assertEqual(self.post(HOUSE,'mode',{'mode':'SIMULATION'}).status_code,200)
        self.assertEqual(self.get(POST),before)
        self.assertEqual(self.post(HOUSE,'mode',{'mode':'PRESENTATION'}).status_code,422)
        self.assertEqual(self.get(HOUSE)['mode'],'SIMULATION')
    def test_05_original_16_scenes_exact(self):
        scenes=json.loads((ROOT/'src/gie_control/assets/scenes.json').read_text(encoding='utf-8'))['scenes']
        self.post(COMM,'mode',{'mode':'PRESENTATION'})
        for scene in scenes:
            r=self.post(COMM,'presentation',{'action':'scene','scene_id':scene['id']})
            self.assertEqual(r.status_code,200,r.text)
            expected=copy.deepcopy(scene['result']);expected['mode']='PRESENTATION'
            self.assertEqual(r.json()['state'],expected)
        self.assertEqual(self.get(HOUSE)['mode'],'SIMULATION')
        for action in ['start','pause','resume','stop','reset','next','previous']:
            self.assertEqual(self.post(COMM,'presentation',{'action':action}).status_code,200)
        self.assertEqual(self.post(COMM,'presentation',{'action':'scene'}).status_code,422)
    def test_06_current_demand_house_guard(self):
        body={'issue_time':'2025-10-01T12:15:00-03:00','current':{'building_kw':0.2,'solar_kw':0.,'demands':[{'evse_id':'EVSE_01','connected':True,'requested_kw':7.}]}}
        r=self.post(HOUSE,'cycle',body);self.assertEqual(r.status_code,200,r.text)
        x=r.json()['state']['station_extension']
        self.assertEqual(x['immediate_demand_kw'],7.)
        self.assertFalse(x['ev_motor2_autonomous_approved']);self.assertAlmostEqual(x['residential_ev_recall'],.06778169014084508)
        self.assertTrue(all(v==7 for v in x['conservative_capacity_envelope_kw']))
        self.assertFalse(x['envelope_is_command']);self.assertFalse(x['envelope_is_quantile'])
    def test_07_physical_envelope_not_other_station(self):
        before=self.get(HOUSE)
        body={'issue_time':'2025-10-01T12:30:00-03:00','current':{'building_kw':1,'solar_kw':0,'demands':[{'evse_id':'EVSE_01','connected':True,'requested_kw':22}]}}
        self.assertEqual(self.post(HOUSE,'cycle',body).status_code,422)
        body['current']['demands'][0].update(evse_id='EVSE4',requested_kw=7)
        self.assertEqual(self.post(HOUSE,'cycle',body).status_code,422)
        self.assertEqual(self.get(HOUSE),before)
        self.assertEqual(self.post(HOUSE,'cycle',{'issue_time':'2025-10-01T12:30:00'}).status_code,422)
        self.assertEqual(self.post(HOUSE,'cycle',{'issue_time':'2025-10-01T12:15:00-03:00'}).status_code,422)
    def test_08_concurrent_same_station_serialized(self):
        revision=self.get(POST)['revision']
        with cf.ThreadPoolExecutor(6) as pool:
            replies=list(pool.map(lambda _:self.post(POST,'mode',{'mode':'SIMULATION'}),range(6)))
        self.assertTrue(all(r.status_code==200 for r in replies))
        self.assertEqual(self.get(POST)['revision'],revision+6)
    def test_09_process_crash_isolation_recovery(self):
        other=self.get(HOUSE);old=self.get(POST);m=self.app.state.manager
        p=m.slots[POST]['process'];p.terminate();p.join(5)
        self.assertEqual(self.client.get('/v1/stations/'+POST+'/state',headers=self.headers).status_code,503)
        self.assertEqual(self.get(HOUSE),other)
        r=self.post(POST,'restart');self.assertEqual(r.status_code,200,r.text)
        new=r.json();self.assertNotEqual(new['generation'],old['generation']);self.assertIsNone(new['state'])
        self.assertEqual(new['history'],[]);self.assertEqual(new['cache'],{});self.assertEqual(new['mode'],'NORMAL')
        self.assertEqual(self.post(POST,'cycle').status_code,200)
    def test_10_stop_and_initialize_idempotent(self):
        before=self.get(HOUSE)
        self.assertEqual(self.post(HOUSE,'initialize').json()['pid'],before['pid'])
        self.assertEqual(self.post(HOUSE,'stop').json()['status'],'stopped')
        self.assertEqual(self.post(HOUSE,'stop').json()['status'],'stopped')
        self.assertEqual(self.client.get('/v1/stations/'+HOUSE+'/state',headers=self.headers).status_code,503)
        self.assertEqual(self.post(HOUSE,'initialize').status_code,200)
    def test_11_journals_isolated(self):
        for sid in [COMM,POST,HOUSE]:
            folder=Path(self.temp.name)/sid
            entries=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines()]
            self.assertTrue(entries);self.assertTrue(all(e['station_id']==sid for e in entries))
            self.assertTrue(all(not e['hardware_commands_sent'] for e in entries))
    def test_12_single_manager_owner(self):
        with self.assertRaises(RuntimeError):Manager(self.temp.name)
    def test_13_commercial_manual_and_normal_preserved(self):
        self.assertEqual(self.post(COMM,'mode',{'mode':'MANUAL_DEMO'}).status_code,200)
        r=self.post(COMM,'manual-demo/event',{'event':'RESET'})
        self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['state']['presentation_metadata']['hardware_commands_sent'])
        self.assertEqual(self.post(COMM,'mode',{'mode':'NORMAL'}).status_code,200)
        r=self.post(COMM,'cycle',{'issue_time':'2026-06-15T12:15:00-03:00'})
        self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['state']['execution_allowed'])
    def test_14_timeout_only_stops_target(self):
        m=self.app.state.manager;other=self.get(HOUSE);previous=m.timeout
        try:
            m.timeout=.000001
            r=self.post(POST,'cycle',{'issue_time':'2025-10-01T12:15:00-03:00'})
            self.assertEqual(r.status_code,503,r.text)
        finally:m.timeout=previous
        self.assertEqual(self.get(HOUSE),other)
        self.assertEqual(self.post(POST,'restart').status_code,200)
    def test_15_service_restart_controlled_recovery(self):
        with tempfile.TemporaryDirectory(prefix='gie-recovery-') as directory:
            first=Manager(directory)
            try:
                old=first.start(HOUSE)
                first.request(HOUSE,'mode',{'mode':'SIMULATION'})
            finally:first.close()
            second=Manager(directory)
            try:
                new=second.start(HOUSE)
                self.assertEqual(new['mode'],'NORMAL');self.assertIsNone(new['state'])
                self.assertNotEqual(new['generation'],old['generation'])
                self.assertEqual(new['history'],[])
                self.assertTrue((Path(directory)/HOUSE/'events.jsonl').is_file())
            finally:second.close()
    def test_16_concurrent_health_and_lifecycle(self):
        m=self.app.state.manager
        def inspect(_):
            return m.health(HOUSE)['status']
        with cf.ThreadPoolExecutor(5) as pool:
            stop=pool.submit(m.stop,HOUSE)
            results=list(pool.map(inspect,range(15)))
            stop.result()
        self.assertTrue(all(x in ('running','stopped') for x in results))
        self.assertEqual(self.post(HOUSE,'initialize').status_code,200)
    def test_17_previous_files_preserved(self):
        before=json.loads((ROOT/'reports/multistation/v1/preservation_before.json').read_text(encoding='utf-8'))
        changed=[p for p,h in before.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
        self.assertEqual(changed,[])

if __name__=='__main__':unittest.main(verbosity=2)
