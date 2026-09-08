import sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
import numpy as np
import pandas as pd
from types import SimpleNamespace
from motor_gerenciamento.config import Config
from motor_gerenciamento.state import State,ForecastInputs
from motor_gerenciamento.optimizer import optimize
from motor_gerenciamento.constraints import Layout
from motor_gerenciamento.validation import MaterialSimultaneityError
from motor_gerenciamento.adapters import aligned_inputs
from motor_gerenciamento.dispatch import apply_first
C=Config()
def inputs(b=100,ev=20,q=40,pv=0,price=.5):
    def a(v):return np.full(48,v,dtype=float) if np.isscalar(v) else np.asarray(v,dtype=float)
    return ForecastInputs(pd.date_range('2026-08-01',periods=48,freq='15min'),a(b),a(ev),a(q),a(.4),a(pv),a(price),a(.08),provenance={'test':'fictitious'})
class MPCV1Tests(unittest.TestCase):
    def check(self,result):
        self.assertTrue(result['execution_allowed']);self.assertEqual(len(result['plan']),48)
        self.assertTrue(result['validation']['valid']);self.assertLessEqual(result['validation']['max_power_balance_error_kw'],1e-5)
        for r in result['plan']:
            self.assertGreaterEqual(r['battery_soc_after_pct'],20-1e-6);self.assertLessEqual(r['battery_soc_after_pct'],95+1e-6)
            self.assertLessEqual(r['grid_import_plan_kw'],350+1e-6);self.assertLessEqual(r['grid_export_plan_kw'],150+1e-6)
            self.assertLessEqual(max(r['battery_charge_kw'],r['battery_discharge_kw']),100+1e-6)
            self.assertAlmostEqual(sum(v for k,v in r['flows'].items() if k.startswith('solar_to_')),r['solar_utilizado_kw'],places=5)
    def test_sunny_low_demand_charges(self):
        r=optimize(inputs(b=np.r_[np.full(24,20),np.full(24,200)],ev=0,q=0,pv=np.r_[np.full(24,125),np.zeros(24)]),State(35));self.check(r)
        self.assertGreater(max(x['battery_charge_kw'] for x in r['plan']),1)
    def test_night_building_ev_peak(self):
        r=optimize(inputs(b=310,ev=70,q=88),State(80));self.check(r)
        self.assertGreater(sum(x['battery_discharge_kw'] for x in r['plan']),1)
    def test_near_minimum_soc(self):self.check(optimize(inputs(b=340,ev=50,q=70),State(20.01)))
    def test_full_battery_exports_solar(self):
        r=optimize(inputs(b=10,ev=0,q=0,pv=125),State(95));self.check(r);self.assertAlmostEqual(r['grid_export_plan_kw'],115,places=4)
    def test_no_ev(self):
        r=optimize(inputs(ev=0,q=0),State(50));self.check(r);self.assertTrue(all(abs(x['ev_block_limit_kw'])<1e-5 for x in r['plan']))
    def test_above_target_below_physical(self):
        r=optimize(inputs(b=330,ev=0,q=0),State(20));self.check(r);self.assertGreater(r['grid_import_plan_kw'],300)
    def test_ev_block_reduction(self):
        r=optimize(inputs(b=290,ev=80,q=88),State(20));self.check(r);self.assertLess(r['ev_block_limit_kw'],80)
    def test_q90_headroom_is_not_free(self):
        r=optimize(inputs(b=290,ev=5,q=88),State(20));self.check(r);self.assertLess(r['ev_block_limit_kw'],88)
        for x in r['plan']:self.assertLessEqual(x['grid_import_plan_kw']-x['grid_export_plan_kw']+x['ev_block_limit_kw']-x['ev_served_kw'],350+1e-6)
    def test_q90_does_not_consume_energy(self):
        r=optimize(inputs(b=0,ev=0,q=88),State(30));self.check(r)
        self.assertTrue(all(abs(x['ev_served_kw'])<1e-6 for x in r['plan']))
    def test_solver_unavailable_fallback(self):
        def broken(*args,**kwargs):raise RuntimeError('deliberately unavailable')
        r=optimize(inputs(),State(50),solver=broken);self.check(r);self.assertTrue(r['fallback_used'])
    def test_invalid_solver_solution_fallback(self):
        def invalid(cost,**kwargs):return SimpleNamespace(success=True,x=np.full(len(cost),np.nan),fun=np.nan)
        r=optimize(inputs(),State(50),solver=invalid);self.check(r);self.assertTrue(r['fallback_used'])
    def test_physically_impossible_blocks_execution(self):
        r=optimize(inputs(b=500,ev=0,q=0),State(20));self.assertFalse(r['execution_allowed']);self.assertTrue(r['fallback_used'])
    def test_material_battery_simultaneity_stops(self):
        def bad(cost,**kwargs):
            x=np.zeros(len(cost));l=Layout(48);x[l.at('battery_charge_kw',0)]=10;x[l.at('battery_discharge_kw',0)]=10
            return SimpleNamespace(success=True,x=x,fun=0)
        with self.assertRaises(MaterialSimultaneityError):optimize(inputs(),State(50),solver=bad)
    def test_material_grid_simultaneity_stops(self):
        def bad(cost,**kwargs):
            x=np.zeros(len(cost));l=Layout(48);x[l.at('grid_import_kw',0)]=10;x[l.at('grid_export_kw',0)]=10
            return SimpleNamespace(success=True,x=x,fun=0)
        with self.assertRaises(MaterialSimultaneityError):optimize(inputs(),State(50),solver=bad)
    def test_timestamp_mismatch_rejected(self):
        a=pd.DataFrame({'timestamp_previsto':pd.date_range('2026-08-01',periods=48,freq='15min')})
        b=a.copy();b.timestamp_previsto+=pd.Timedelta(minutes=15)
        with self.assertRaises(ValueError):aligned_inputs(a,b,np.zeros(48),np.ones(48),np.zeros(48))
    def test_wrong_horizon_rejected(self):
        p=inputs();p.timestamps=p.timestamps[:-1]
        with self.assertRaises(ValueError):optimize(p,State(50))
    def test_arbitrage_tariff_rejected(self):
        p=inputs();p.export_credit_kwh=np.full(48,2.)
        with self.assertRaises(ValueError):optimize(p,State(50))
    def test_actual_measurement_guard(self):
        result=optimize(inputs(b=100,ev=20,q=50),State(20));self.check(result)
        row=apply_first(result['first_decision'],State(20),345,88,0,C)
        self.assertLessEqual(row['grid_import_plan_kw'],350+1e-6);self.assertTrue(row['safety_override']);self.assertLessEqual(row['ev_served_kw'],5+1e-6)
    def test_first_decision_only_changes_state(self):
        s=State(50);r=optimize(inputs(),s);row=apply_first(r['first_decision'],s,100,20,0,C)
        expected=100+.25*(row['battery_charge_kw']*.95-row['battery_discharge_kw']/.95)
        self.assertAlmostEqual(row['battery_energy_kwh'],expected,places=6)
    def test_solar_above_inverter_rejected(self):
        with self.assertRaises(ValueError):optimize(inputs(pv=126),State(50))
if __name__=='__main__':unittest.main()
