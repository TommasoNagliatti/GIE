import json,unittest
from pathlib import Path
from gie_panel.flow import svg,accumulated
from gie_panel.comparison import summarize,OUT

class FlowTests(unittest.TestCase):
    def test_no_false_flows_or_house_battery(self):
        s=svg(dict(solar_kw=0,grid_import_kw=1,grid_export_kw=0,building_kw=1,ev_served_kw=0),{'batteries':[]},{})
        self.assertIn('data-flow="import"',s);self.assertIn('data-flow="building"',s)
        for node in ('solar','export','ev'):self.assertNotIn('data-flow="'+node+'"',s)
        self.assertNotIn('BAT_',s)
    def test_batteries_individual_and_direction(self):
        eq={'batteries':[{'battery_id':'BAT_01'},{'battery_id':'BAT_02'}]}
        first={'batteries':{'BAT_01':{'charge_kw':2,'discharge_kw':0},'BAT_02':{'charge_kw':0,'discharge_kw':1}}}
        s=svg({},eq,first)
        self.assertIn('BAT_01',s);self.assertIn('BAT_02',s);self.assertIn('Carregando',s);self.assertIn('Descarregando',s)
        self.assertEqual(s.count('data-flow='),2)
    def test_unknown_is_not_zero(self):
        s=svg({}, {'batteries':[]},{})
        self.assertNotIn('data-flow=',s);self.assertIn('Não informado',s)
    def test_accumulation_rejects_scene_jumps_and_duplicate_times(self):
        row=dict(timestamp='2025-11-01T00:00:00-03:00',solar_kw=4,building_kw=1,ev_served_kw=0,grid_import_kw=0,grid_export_kw=3)
        self.assertEqual(accumulated([row],'NORMAL')['solar_kw'],1)
        self.assertIsNone(accumulated([row,row],'NORMAL'))
        self.assertIsNone(accumulated([row],'PRESENTATION'))
        self.assertIsNone(accumulated([dict(row,solar_kw=None)],'REPLAY'))

class PairedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=json.loads((OUT/'result.json').read_text(encoding='utf-8'))
    def test_all_intervals_and_same_inputs(self):
        p=self.result['periods']['Novembro · 30 dias']
        self.assertEqual(len(p['rows']['A']),2880);self.assertEqual(len(p['rows']['B']),2880)
        for a,b in zip(p['rows']['A'],p['rows']['B']):
            for k in ['timestamp','solar_kw','building_kw','ev_demand_kw']:self.assertEqual(a[k],b[k])
            for r in (a,b):
                self.assertLess(abs(r['solar_used_kw']+r['grid_import_kw']+r['discharge_kw']-r['building_kw']-r['ev_served_kw']-r['charge_kw']-r['grid_export_kw']),2e-5)
                self.assertLess(abs(r['stored_kwh']-r['initial_kwh']-.25*(.95*r['charge_kw']-r['discharge_kw']/.95)),2e-5)
                self.assertLess(abs(r['solar_kw']-r['solar_used_kw']-r['curtailed_kw']),2e-5)
                self.assertLessEqual(r['grid_import_kw'],17+1e-5);self.assertLessEqual(r['grid_export_kw'],6+1e-5)
            self.assertGreaterEqual(b['soc_pct'],20-1e-5);self.assertLessEqual(b['soc_pct'],95+1e-5)
            self.assertLessEqual(b['charge_kw'],2.2+1e-5);self.assertLessEqual(b['discharge_kw'],2.2+1e-5)
    def test_integrals_for_all_periods(self):
        for p in self.result['periods'].values():
            for v in ('A','B'):
                s=summarize(p['rows'][v]);self.assertEqual(s,p['summary'][v])
                self.assertLess(abs(s['ac_balance_error_kwh']),1e-4);self.assertLess(abs(s['storage_balance_error_kwh']),1e-4)
        self.assertGreater(self.result['periods']['Dia com EV']['summary']['A']['ev_requested_kwh'],0)
        self.assertEqual(self.result['periods']['Dia sem EV']['summary']['A']['ev_requested_kwh'],0)
    def test_solver_residual_not_classified_as_charger_limit(self):
        for case in self.result['periods']['Novembro · 30 dias']['summary'].values():
            self.assertGreater(case['ev_unserved_kwh'],0)  # Raw precision retained.
            self.assertLess(case['max_ev_residual_kw'],case['ev_limit_display_threshold_kw'])
            self.assertEqual(case['limited_intervals'],0)
    def test_configuration_and_checkpoint_isolation(self):
        a=self.result['configurations']['A'];b=self.result['configurations']['B']
        self.assertEqual(a['batteries'],[])
        self.assertEqual({k:v for k,v in a.items() if k!='batteries'},{k:v for k,v in b.items() if k!='batteries'})
        self.assertNotEqual(self.result['checkpoint_paths']['A'],self.result['checkpoint_paths']['B'])
    def test_inputs_still_identical(self):
        import hashlib
        root=Path(__file__).resolve().parents[2]
        for name,expected in self.result['inputs_sha256'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),expected,name)

class ComparisonAPITests(unittest.TestCase):
    def test_authorization_and_station_scope(self):
        import tempfile
        from fastapi.testclient import TestClient
        from gie_multistation.api import create_app
        token='comparison-test-token-'+'x'*30
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with TestClient(create_app(tokens={token:['DEMO_CASA_001','DEMO_POSTO_24H_001']},data_dir=root/'registry',panel_dir=root/'panel')) as c:
                path='/panel/DEMO_CASA_001/comparison'
                self.assertEqual(c.get(path).status_code,401)
                h={'Authorization':'Bearer '+token}
                response=c.get(path,headers=h)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['status'],'complete')
                self.assertEqual(response.json()['result']['cycles_per_case'],2880)
                self.assertEqual(c.get('/panel/DEMO_POSTO_24H_001/comparison',headers=h).status_code,404)
                self.assertEqual(c.get('/panel/Commercial_HighAutonomy_V2/comparison',headers=h).status_code,403)

if __name__=='__main__':unittest.main()
