import sys,json,unittest,tempfile,socket,hashlib,importlib.util
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from observabilidade import build_trace,DecisionLog
from observabilidade.run import observe_cycle
from demo.session import ReplaySession,LiveGate
FRAMES=[json.loads(x) for x in (ROOT/'outputs/observabilidade/v1/replay_cycles.jsonl').read_text(encoding='utf-8').splitlines()]
class TraceTests(unittest.TestCase):
    def decision(self,i,key):return next(d for d in FRAMES[i]['trace']['decisions'] if d['action']==key)
    def test_no_change(self):
        c=FRAMES[0]['cycle'];self.assertEqual(build_trace(c,build_trace(c))['changes'],[])
    def test_charge(self):
        d=self.decision(1,'battery_charge_kw');self.assertAlmostEqual(d['new_value'],78);self.assertIn('SOLAR_SURPLUS',d['reason_codes'])
    def test_discharge(self):self.assertGreater(self.decision(2,'battery_discharge_kw')['new_value'],0)
    def test_ev_limited(self):self.assertIn('EV_POWER_LIMITED',self.decision(5,'ev_block_limit_kw')['reason_codes'])
    def test_fault(self):
        d=self.decision(4,'evse_3_kw');self.assertEqual(d['new_value'],0);self.assertIn('EVSE_FAULT',d['reason_codes'])
    def test_export(self):
        d=self.decision(6,'grid_export_plan_kw');self.assertAlmostEqual(d['new_value'],90);self.assertIn('GRID_EXPORT_SURPLUS',d['reason_codes'])
    def test_forecast_above_actual(self):self.assertIn('EV_FORECAST_ABOVE_REALIZED',[e['code'] for e in FRAMES[0]['trace']['events']])
    def test_critical(self):self.assertTrue(any(e['severity']=='critical' for e in FRAMES[7]['trace']['events']))
    def test_blocked_no_commands(self):self.assertEqual([d['action'] for d in FRAMES[7]['trace']['decisions']],['execution_allowed'])
    def test_json(self):
        for f in FRAMES:json.dumps(f['trace'],allow_nan=False)
    def test_compact(self):
        c=FRAMES[1]['trace']['llm_context'];self.assertFalse(c['api_called']);self.assertNotIn('forecasts',c);self.assertLessEqual(len(c['decisions']),10)
    def test_readonly(self):
        c=deepcopy(FRAMES[0]['cycle']);old=deepcopy(c);observe_cycle(c);self.assertEqual(c,old)
    def test_offline(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            r=ReplaySession(ROOT/'outputs/observabilidade/v1/replay_cycles.jsonl');r.advance(1);self.assertEqual(r.index,1)
    def test_replay_copy(self):
        r=ReplaySession(ROOT/'outputs/observabilidade/v1/replay_cycles.jsonl');r.current()['cycle']['status']='bad';self.assertNotEqual(r.current()['cycle']['status'],'bad')
    def test_bounded_play(self):
        r=ReplaySession(ROOT/'outputs/observabilidade/v1/replay_cycles.jsonl');r.playing=True;r.advance(0,True);self.assertFalse(r.advance(1,True));self.assertTrue(r.advance(8,True));r.reset();self.assertEqual(r.index,0)
    def test_live_gate(self):
        g=LiveGate();self.assertTrue(g.begin(0));g.end();self.assertFalse(g.begin(29));self.assertTrue(g.begin(30))
    def test_log(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'outputs/observabilidade') as d:
            p=Path(d)/'events.jsonl';log=DecisionLog(p);n=log.append(FRAMES[1]['trace']);self.assertGreater(n,0);self.assertEqual(log.append(FRAMES[1]['trace']),0)
            self.assertEqual(DecisionLog(p).append(FRAMES[1]['trace']),0)
            for s in p.read_text(encoding='utf-8').splitlines():
                self.assertTrue({'timestamp','code','severity','component','previous_value','new_value','reason_codes','context'}<=json.loads(s).keys())
    def test_log_failure_visible(self):
        class Broken:
            def append(self,t):raise OSError('disk unavailable')
        self.assertIn('logging_error',observe_cycle(FRAMES[0]['cycle'],logger=Broken())['decision_trace'])
    def test_core_without_streamlit(self):
        self.assertIsNone(importlib.util.find_spec('streamlit'))
        from gie_runtime import run_gie_cycle
        self.assertTrue(callable(run_gie_cycle))
    def test_frozen(self):
        manifest=json.loads((ROOT/'outputs/observabilidade/v1/preservation_before.json').read_text(encoding='utf-8'))
        self.assertEqual([p for p,h in manifest.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h],[])
if __name__=='__main__':unittest.main()
