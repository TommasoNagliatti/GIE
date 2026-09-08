import sys,json,unittest,hashlib
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from demo.simulation.state import Playback,initial,timestamp
from demo.simulation.scenarios import inject
from demo.simulation.engine import Engine,validate_cycle
class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.engine=Engine(ROOT)
    def test_advance(self):
        s=initial();n=self.engine.step(s);self.assertEqual(s["index"],0);self.assertEqual(n["index"],1);self.assertEqual(str(timestamp(n)),"2026-06-15 00:15:00")
    def test_pause(self):
        c=Playback();c.start(10);self.assertTrue(c.due(10));c.pause();self.assertFalse(c.due(100))
    def test_reset(self):
        c=Playback();c.start(0);c.reset();self.assertFalse(c.playing)
        s=self.engine.step(initial());fresh=initial();self.assertEqual(fresh["soc"],50);self.assertEqual(fresh["observations"],[]);self.assertEqual(s["index"],1)
    def test_speed(self):
        c=Playback();c.start(0);c.completed(0,1);c.speed(7.5,5);self.assertAlmostEqual(c.next_due,10);self.assertFalse(c.due(9));self.assertTrue(c.due(10))
    def test_no_catchup(self):
        c=Playback();c.start(0);c.completed(0,20);self.assertGreater(c.next_due,20)
    def test_soc_continuity(self):
        s=initial("2026-06-15 16:00:00");inject(s,"building_peak");inject(s,"ev_peak")
        n=self.engine.step(s);n2=self.engine.step(n)
        self.assertAlmostEqual(n2["rows"][-1]["soc_before_pct"],n["soc"])
        self.assertGreater(n["previous_discharge_kw"],0)
    def test_fault_reaction(self):
        s=initial("2026-06-15 15:00:00");inject(s,"ev_peak");inject(s,"fault_3")
        n=self.engine.step(s);c=n["last_frame"]["cycle"]
        self.assertEqual(c["load_balancer"]["evse_3_kw"],0)
        self.assertTrue(any(e["code"]=="EVSE_FAULT" for e in c["events"]));validate_cycle(c)
    def test_ev_peak(self):
        s=initial();inject(s,"ev_peak");cur,_,ev,_=self.engine.telemetry.sample(s)
        self.assertEqual(cur.ev_demand_kw,88);self.assertEqual(ev.carros_chegando,6);self.assertEqual(sum(d.connected for d in cur.evses),4)
    def test_solar_drop(self):
        s=initial("2026-06-15 12:00:00");base=self.engine.telemetry.sample(deepcopy(s))[0];inject(s,"solar_drop");actual=self.engine.telemetry.sample(s)[0]
        self.assertAlmostEqual(actual.solar_kw,base.solar_kw*.15)
    def test_building_peak(self):
        s=initial();base=self.engine.telemetry.sample(deepcopy(s))[0];inject(s,"building_peak");actual=self.engine.telemetry.sample(s)[0]
        self.assertAlmostEqual(actual.building_kw,base.building_kw+160)
    def test_event_expiry(self):
        s=initial();inject(s,"fault_1",1);s["index"]=1;cur=self.engine.telemetry.sample(s)[0];self.assertNotEqual(cur.evses[0].state,"fault")
    def test_history_no_future(self):
        s=initial();base=self.engine.telemetry.history(s);inject(s,"building_peak")
        self.assertTrue(base.building.equals(self.engine.telemetry.history(s).building))
        n=self.engine.step(s);h=self.engine.telemetry.history(n)
        self.assertEqual(h.building.iloc[-1].consumo_predio_kw,n["rows"][-1]["building_kw"])
    def test_full_day_and_limits(self):
        f=json.loads((ROOT/"outputs/simulation/v1/run_24h/simulation.json").read_text(encoding="utf-8"))
        self.assertEqual(len(f["cycles"]),96);prev=50
        for frame in f["cycles"]:
            c=frame["cycle"];validate_cycle(c);self.assertAlmostEqual(c["current_state"]["battery_soc_pct"],prev);prev=c["management"]["battery_soc_after_pct"]
        self.assertEqual(f["cycles"][-1]["cycle"]["decision_time"],"2026-06-15 23:45:00")
    def test_complete_stops(self):
        s=initial();s["index"]=96
        with self.assertRaises(ValueError):self.engine.step(s)
    def test_blocked_does_not_advance(self):
        class Broken:
            def predict(self,*a):raise RuntimeError("test failure")
        from gie_runtime import Components
        e=Engine(ROOT,Components(Broken(),self.engine.components.motor2,self.engine.components.solar))
        n=e.step(initial());self.assertTrue(n["stopped"]);self.assertEqual(n["index"],0);self.assertEqual(n["soc"],50)
    def test_offline(self):
        import socket
        with patch.object(socket,"socket",side_effect=AssertionError("No network")):
            self.assertEqual(self.engine.step(initial())["index"],1)
    def test_preservation(self):
        m=json.loads((ROOT/"outputs/simulation/v1/preservation_before.json").read_text(encoding="utf-8"))
        self.assertEqual([p for p,h in m.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h],[])
if __name__=="__main__":unittest.main()
