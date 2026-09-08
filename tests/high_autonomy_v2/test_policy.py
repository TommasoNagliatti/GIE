import sys,json,unittest,hashlib
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"src"))
from motor_gerenciamento_v2.policy import run_control
from motor_gerenciamento_v2.config import Config
from motor_gerenciamento.state import State,Measurements
from motor_gerenciamento.validation import validate_plan
class Tests(unittest.TestCase):
 def case(self,b=100,ev=0,pv=0,soc=50):
  ix=pd.date_range("2026-06-15",periods=48,freq="15min")
  a=pd.DataFrame({"timestamp_previsto":ix,"consumo_previsto_kw":[b]+[0]*47})
  e=pd.DataFrame({"timestamp_previsto":ix,"potencia_solicitada_prevista_kw":[ev]+[0]*47,"potencia_solicitada_alta_kw":[ev]+[0]*47,"probabilidade_fila":0})
  r=run_control(a,e,pd.Series([pv]+[0]*47,index=ix),state=State(soc),execution_measurements=Measurements(ix[0],b,ev,pv))
  self.assertFalse(r["fallback_used"]);validate_plan(r["plan"],State(soc),Config());return r["first_decision"]
 def test_01_discharge(self):self.assertAlmostEqual(self.case()["battery_discharge_kw"],100,places=4)
 def test_02_minimum(self):self.assertAlmostEqual(self.case(soc=20.5)["battery_soc_after_pct"],20,places=5)
 def test_03_no_reserve(self):
  c=Config();self.assertEqual(c.energy_reserve+c.weight_cycle+c.weight_reserve+c.weight_terminal_reserve,0)
  self.assertGreater(self.case(soc=20.5)["battery_discharge_kw"],0)
 def test_04_no_grid_charge(self):
  r=self.case(soc=20);self.assertEqual(r["battery_charge_kw"],0);self.assertEqual(r["flows"].get("grid_to_battery_kw",0),0)
 def test_05_surplus_charge(self):self.assertAlmostEqual(self.case(b=25,ev=10,pv=500)["battery_charge_kw"],450,places=4)
 def test_06_full_export(self):self.assertAlmostEqual(self.case(b=25,ev=10,pv=500,soc=95)["grid_export_plan_kw"],465,places=4)
 def test_07_simultaneity(self):
  for r in [self.case(),self.case(pv=500)]:self.assertLess(min(r["battery_charge_kw"],r["battery_discharge_kw"]),1e-5)
 def test_08_soc(self):
  for soc in [20,20.5,50,94.9,95]:
   r=self.case(pv=500,soc=soc);self.assertTrue(20-1e-6<=r["battery_soc_after_pct"]<=95+1e-6)
 def test_09_power(self):self.assertAlmostEqual(self.case(b=700,ev=88)["battery_discharge_kw"],450,places=4)
 def test_10_import(self):self.assertAlmostEqual(self.case(soc=20.5)["grid_import_plan_kw"],62,places=4)
 def test_11_building(self):
  r=self.case(b=700,ev=88);self.assertAlmostEqual(sum(r["flows"].get(x+"_to_building_kw",0) for x in ["solar","battery","grid"]),700)
 def test_12_ev(self):self.assertAlmostEqual(self.case(b=340,ev=88,soc=20)["ev_served_kw"],10,places=4)
 def test_13_balance(self):
  for r in [self.case(),self.case(pv=500),self.case(b=340,ev=88,soc=20)]:
   self.assertAlmostEqual(r["solar_utilizado_kw"]+r["grid_import_plan_kw"]+r["battery_discharge_kw"],r["building_kw"]+r["ev_served_kw"]+r["battery_charge_kw"]+r["grid_export_plan_kw"],places=4)
 def test_14_preservation(self):
  m=json.loads((ROOT/"outputs/high_autonomy_v2/preservation_before.json").read_text(encoding="utf-8"))
  self.assertEqual([p for p,h in m.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h],[])
 def test_15_identical_inputs(self):
  a=json.loads((ROOT/"outputs/simulation/v1/run_24h/simulation.json").read_text(encoding="utf-8"))["cycles"]
  b=json.loads((ROOT/"outputs/high_autonomy_v2/comparison/v2_cycles.json").read_text(encoding="utf-8"));self.assertEqual(len(b),96)
  for x,y in zip(a,b):
   for k in ["building_kw","ev_demand_kw","evses","timestamp"]:self.assertEqual(x["cycle"]["current_state"][k],y["cycle"]["current_state"][k])
   for u,v in zip(x["cycle"]["forecasts"]["records"],y["cycle"]["forecasts"]["records"]):
    for k in u:
     if k!="solar_previsto_kw":self.assertEqual(u[k],v[k])
 def test_16_all_plans(self):
  for f in json.loads((ROOT/"outputs/high_autonomy_v2/comparison/v2_cycles.json").read_text(encoding="utf-8")):
   c=f["cycle"];validate_plan(c["management"]["plan"],State(c["current_state"]["battery_soc_pct"]),Config());self.assertLess(c["management"]["power_balance_error_kw"],1e-5)
 def test_17_namespace(self):
  from gie_runtime.orchestrator import run_gie_cycle
  from motor_gerenciamento.run import run_control as old
  from motor_gerenciamento_v2.runtime_adapter import cycle_impl
  self.assertIs(run_gie_cycle.__globals__["run_control"],old);self.assertIs(cycle_impl.__code__,run_gie_cycle.__code__)
 def test_18_must_use(self):self.assertEqual(self.case(pv=500,soc=95)["solar_utilizado_kw"],500)
if __name__=="__main__":unittest.main()
