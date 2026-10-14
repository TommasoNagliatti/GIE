import json,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from gie_multistation.api import create_app
from gie_panel.alerts import Alerts,condition,detect
from gie_panel.data import COMM,POST,HOUSE,NEW,ROOT

TOKEN='panel-test-only-'+'x'*30

class AlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.file=Path(self.tmp.name)/'alerts.sqlite';self.a=Alerts(self.file)
    def tearDown(self):self.a.close();self.tmp.cleanup()
    def observe(self,source,conditions,domains=('energy',),sid='A'):self.a.observe(sid,'g1','2026-10-13T10:00:00Z',source,conditions,set(domains))
    def test_dedup_ack_recovery_reopen_restart_isolation(self):
        c=condition('FAULT','Falha',severity='critical',equipment='EV1')
        self.observe('1',[c]);self.observe('1',[c]);self.observe('2',[c])
        a=self.a.list('A')[0];self.assertEqual(a['occurrence_count'],1);self.assertEqual(len(self.a.history('A')),2)
        self.a.ack('A',a['alert_id']);self.assertEqual(self.a.list('A')[0]['status'],'ACKNOWLEDGED')
        self.a.close();self.a=Alerts(self.file);self.observe('3',[],domains=())
        self.assertEqual(self.a.list('A')[0]['status'],'ACKNOWLEDGED');self.assertEqual(self.a.list('B'),[])
        with self.assertRaises(KeyError):self.a.ack('B',a['alert_id'])
        self.observe('4',[]);self.assertNotEqual(self.a.list('A')[0]['status'],'RESOLVED')
        self.observe('5',[]);self.assertEqual(self.a.list('A')[0]['status'],'RESOLVED')
        self.observe('6',[c]);a2=self.a.list('A')[0];self.assertEqual(a2['alert_id'],a['alert_id']);self.assertEqual(a2['occurrence_count'],2)
        self.assertEqual(len(self.a.list('A','critical','OPEN','EV1')),1)
    def test_hysteresis_soc_and_unknown(self):
        eq=dict(import_kw=100,batteries=[dict(battery_id='B',soc_min=.2)],evses=[])
        r=dict(execution_allowed=True,numeric_state=dict(grid_import_kw=96),management=dict(first_decision=dict(batteries={'B':dict(soc_after=.21)})))
        c,_=detect(r,eq);self.assertIn('BATTERY_SOC_MIN',[x['code'] for x in c]);self.assertIn('GRID_NEAR_LIMIT',[x['code'] for x in c])
        r['numeric_state']['grid_import_kw']=93
        self.assertNotIn('GRID_NEAR_LIMIT',[x['code'] for x in detect(r,eq)[0]])
        self.assertIn('GRID_NEAR_LIMIT',[x['code'] for x in detect(r,eq,active=['GRID_NEAR_LIMIT|'])[0]])
        c,domains=detect(dict(execution_allowed=False),eq);self.assertNotIn('energy',domains);self.assertNotIn('BATTERY_SOC_MIN',[x['code'] for x in c])
    def test_baseline_continuing_is_one_occurrence(self):
        for i in range(20):self.observe(str(i),[condition('BASELINE_NO_HISTORY','Baseline','model','info')],('model',))
        self.assertEqual(len(self.a.list('A')),1);self.assertEqual(self.a.list('A')[0]['occurrence_count'],1)
    def test_availability_requires_observation_and_registered_equipment(self):
        eq=dict(import_kw=25,batteries=[dict(battery_id='B',soc_min=.2,discharge_kw=5)],evses=[],inverters=[dict(inverter_id='I')])
        current=dict(battery_available={'B':False,'UNKNOWN':False},inverter_available={'I':False},building_kw=40,solar_kw=0)
        c,domains=detect(dict(execution_allowed=False),eq,current)
        self.assertIn('MANDATORY_LOAD_ABOVE_CAPACITY',[x['code'] for x in c]);self.assertIn('BATTERY_UNAVAILABLE',[x['code'] for x in c]);self.assertIn('INVERTER_UNAVAILABLE',[x['code'] for x in c])
        self.assertNotIn('UNKNOWN',[x['equipment_id'] for x in c]);self.assertIn('battery_availability:B',domains)
        self.assertNotIn('battery_availability:B',detect(dict(execution_allowed=False),eq,{})[1])

class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)
        cls.client=TestClient(create_app(tokens={TOKEN:[COMM,POST,HOUSE,NEW]},data_dir=p/'registry',panel_dir=p/'panel'))
        cls.client.__enter__();cls.client.headers['Authorization']='Bearer '+TOKEN
    @classmethod
    def tearDownClass(cls):cls.client.__exit__(None,None,None);cls.tmp.cleanup()
    def request(self,sid,op,body=None):
        r=self.client.get('/panel/'+sid+'/'+op) if body is None else self.client.post('/panel/'+sid+'/'+op,json=body)
        self.assertEqual(r.status_code,200,r.text[:1500]);return r.json()
    def test_01_four_station_replays_read_only(self):
        for sid,count in [(COMM,1),(POST,2),(HOUSE,0),(NEW,0)]:
            cat=self.request(sid,'catalog');self.assertEqual(len(cat['equipment']['batteries']),count)
            for scenario in cat['scenarios']:
                r=self.request(sid,'replay?scenario='+scenario['id']+'&index=0');v=r['view']
                self.assertEqual(v['station_id'],sid);self.assertFalse(v['result']['physical_dispatch']);self.assertFalse(v['result']['visual_state']['commands_valid'])
                self.assertEqual(self.request(sid,'alerts'),[])
            if sid in (POST,HOUSE):self.assertEqual(len(self.request(sid,'replay?scenario=spring')['view']['result']['forecasts']['records']),48)
        self.assertEqual(self.client.get('/panel/'+POST+'/state',headers={'Authorization':'Bearer wrong'}).status_code,401)
    def test_02_baseline_blocked_recovery_restart(self):
        self.request(NEW,'reset',{'scenario':'baseline'})
        missing=self.request(NEW,'cycle',{'fixture':'missing'})
        self.assertFalse(missing['view']['result']['execution_allowed']);self.assertIsNone(missing['view']['result']['numeric_state'].get('building_kw'))
        bad=self.request(NEW,'cycle',{'fixture':'overload'});self.assertFalse(bad['view']['result']['execution_allowed'])
        before=self.request(NEW,'alerts');self.assertTrue(any(a['severity']=='critical' for a in before),before)
        critical=next(a for a in before if a['severity']=='critical');self.request(NEW,'alerts/'+critical['alert_id']+'/ack',{})
        self.request(NEW,'restart',{});self.assertEqual(next(a for a in self.request(NEW,'alerts') if a['alert_id']==critical['alert_id'])['status'],'ACKNOWLEDGED')
        for i in range(2):r=self.request(NEW,'cycle',{'fixture':'normal'});self.assertTrue(r['view']['result']['execution_allowed'])
        self.assertEqual(next(a for a in self.request(NEW,'alerts') if a['alert_id']==critical['alert_id'])['status'],'RESOLVED')
        a=next(a for a in self.request(NEW,'alerts') if a['code']=='BASELINE_NO_HISTORY');self.assertEqual(a['occurrence_count'],1)
    def test_03_commercial_16_scenes_and_fault_recovery(self):
        self.request(COMM,'reset',{'scenario':'commercial'});self.request(COMM,'mode',{'mode':'PRESENTATION'})
        for i in range(1,17):
            r=self.request(COMM,'presentation',{'action':'scene','scene_id':f'{i:02d}'})
            self.assertEqual(r['presentation']['scene_id'],f'{i:02d}');self.assertFalse(r['view']['result']['hardware_commands_sent'])
            if i==13:self.assertTrue(any(a['code']=='EVSE_FAULT' and a['equipment_id']=='EVSE3' for a in self.request(COMM,'alerts')))
            if i==14:
                for j in range(3):self.request(COMM,'state')
                self.assertNotEqual(next(a for a in self.request(COMM,'alerts') if a['code']=='EVSE_FAULT' and a['equipment_id']=='EVSE3')['status'],'RESOLVED')
        fault=next(a for a in self.request(COMM,'alerts') if a['code']=='EVSE_FAULT' and a['equipment_id']=='EVSE3');self.assertEqual(fault['status'],'RESOLVED')
        self.request(COMM,'mode',{'mode':'MANUAL_DEMO'});self.request(COMM,'manual',{'event':'SOC_LOW'})
        self.assertTrue(any(a['code']=='BATTERY_SOC_MIN' for a in self.request(COMM,'alerts')))
    def test_04_interactive_96_cycles_both_profiles(self):
        evidence={}
        for sid,batteries in [(POST,2),(HOUSE,0)]:
            start=self.request(sid,'reset',{'scenario':'spring'})
            for i in range(96):
                r=self.request(sid,'cycle',{});self.assertEqual(r['cycle'],i+1);self.assertTrue(r['view']['result']['execution_allowed']);self.assertEqual(len(r['view']['result']['forecasts']['records']),48)
                self.assertEqual(len(r['view']['equipment']['batteries']),batteries)
            evidence[sid]=dict(cycles=r['cycle'],history_count=len(r['view']['history']),run_id=start['run_id'],last_result=r['view']['result'])
            old_history=r['view']['history'];self.request(sid,'restart',{});resumed=self.request(sid,'state');self.assertEqual(resumed['cycle'],96);self.assertEqual(resumed['view'],None)
            self.assertEqual(self.client.post('/panel/'+sid+'/cycle',json={}).status_code,422)
        post_run=self.request(POST,'state')['run_id'];self.request(HOUSE,'reset',{'scenario':'summer'});self.assertEqual(self.request(POST,'state')['run_id'],post_run)
        (ROOT/'reports/panel/v1/interactive_96.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')

class FullRestartTests(unittest.TestCase):
    def test_parallel_panel_cycles_and_run_index(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with TestClient(create_app(tokens={TOKEN:[POST,HOUSE]},data_dir=root/'registry',panel_dir=root/'panel'),headers={'Authorization':'Bearer '+TOKEN}) as client:
                def execute(sid):
                    initial=client.post('/panel/'+sid+'/reset',json={'scenario':'spring'})
                    self.assertEqual(initial.status_code,200)
                    for i in range(3):self.assertEqual(client.post('/panel/'+sid+'/cycle',json={}).status_code,200)
                    return client.get('/panel/'+sid+'/state').json()
                with ThreadPoolExecutor(2) as pool:results=list(pool.map(execute,[POST,HOUSE]))
                self.assertEqual([r['view']['station_id'] for r in results],[POST,HOUSE]);self.assertNotEqual(results[0]['run_id'],results[1]['run_id'])
                index=json.loads((root/'panel/runs.json').read_text())
                self.assertEqual([index[s]['index'] for s in [POST,HOUSE]],[3,3])
    def test_alerts_survive_api_restart_stop_resume_and_offline_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def app():return create_app(tokens={TOKEN:[NEW]},data_dir=root/'registry',panel_dir=root/'panel')
            prefix='/panel/'+NEW
            with TestClient(app(),headers={'Authorization':'Bearer '+TOKEN}) as client:
                client.post(prefix+'/initialize')
                self.assertEqual(client.post(prefix+'/cycle',json={'fixture':'overload'}).status_code,200)
                critical=next(a for a in client.get(prefix+'/alerts').json() if a['severity']=='critical')
                alert_id=critical['alert_id'];client.post(prefix+'/alerts/'+alert_id+'/ack')
            with TestClient(app(),headers={'Authorization':'Bearer '+TOKEN}) as client:
                saved=next(a for a in client.get(prefix+'/alerts').json() if a['alert_id']==alert_id)
                self.assertEqual(saved['status'],'ACKNOWLEDGED')
                client.post(prefix+'/initialize')
                client.post(prefix+'/cycle',json={'fixture':'offline'})
                self.assertTrue(any(a['code']=='EVSE_OFFLINE' and a['equipment_id']=='E0' for a in client.get(prefix+'/alerts').json()))
                client.post(prefix+'/stop');self.assertEqual(client.get(prefix+'/state').json()['process'],'stopped')
                client.post(prefix+'/initialize')
                for _ in range(2):self.assertEqual(client.post(prefix+'/cycle',json={}).status_code,200)
                alerts=client.get(prefix+'/alerts').json()
                self.assertEqual(next(a for a in alerts if a['code']=='EVSE_OFFLINE')['status'],'RESOLVED')
                self.assertEqual(next(a for a in alerts if a['alert_id']==alert_id)['status'],'RESOLVED')

if __name__=='__main__':unittest.main()
