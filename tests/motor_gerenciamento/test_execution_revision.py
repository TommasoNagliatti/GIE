import unittest
import numpy as np
from test_mpc import C,inputs
from motor_gerenciamento.state import State
from motor_gerenciamento.dispatch import apply_first
from motor_gerenciamento.events import from_decision
from motor_gerenciamento.validation import PhysicalInfeasibleError

def decision(charge=0,discharge=0):
    return dict(timestamp='2026-08-01 00:00:00',battery_charge_kw=charge,battery_discharge_kw=discharge,ev_block_limit_kw=20,ev_expected_kw=10,ev_high_kw=20)

class ExecutionRevisionTests(unittest.TestCase):
    def test_public_api_uses_fresh_measurements(self):
        from unittest.mock import patch
        from motor_gerenciamento.run import run_control
        from motor_gerenciamento.state import Measurements
        from motor_gerenciamento.optimizer import optimize
        p=inputs();s=State(20)
        planned=optimize(p,s)
        m=Measurements(p.timestamps[0],100,80,0)
        with patch('motor_gerenciamento.run.aligned_inputs',return_value=p):
            r=run_control(None,None,None,None,None,s,execution_measurements=m)
        self.assertEqual(r['first_decision']['ev_served_kw'],80)
        self.assertEqual(r['plan'],planned['plan'])
        self.assertEqual(len(r['plan']),48)
        self.assertEqual(r['ev_block_limit_kw'],80)
    def test_public_api_rejects_stale_measurements(self):
        from unittest.mock import patch
        from motor_gerenciamento.run import run_control
        from motor_gerenciamento.state import Measurements
        p=inputs()
        with patch('motor_gerenciamento.run.aligned_inputs',return_value=p):
            with self.assertRaises(ValueError):run_control(None,None,None,None,None,State(20),execution_measurements=Measurements('2026-07-31 23:45',100,80,0))
    def test_above_q90_available_capacity(self):
        r=apply_first(decision(),State(20),100,80,0,C)
        self.assertEqual(r['ev_served_kw'],80);self.assertEqual(r['ev_unserved_kw'],0)
        events=from_decision(r,State(20),C)
        for code in ['EV_DEMAND_ABOVE_FORECAST','EV_BLOCK_LIMIT_RELAXED']:
            self.assertEqual(next(e['severity'] for e in events if e['code']==code),'info')
        self.assertFalse(r['safety_override'])
    def test_above_q90_insufficient_capacity_maximum(self):
        r=apply_first(decision(),State(21),350,80,0,C)
        self.assertAlmostEqual(r['ev_served_kw'],7.6);self.assertAlmostEqual(r['grid_import_plan_kw'],350)
    def test_ev_physical_cap(self):
        r=apply_first(decision(),State(50),100,120,0,C)
        self.assertEqual(r['ev_served_kw'],88);self.assertLessEqual(r['ev_block_limit_kw'],88)
    def test_grid_cap_cancel_charge_and_discharge(self):
        r=apply_first(decision(charge=100),State(50),340,88,0,C)
        self.assertEqual(r['battery_charge_kw'],0);self.assertAlmostEqual(r['battery_discharge_kw'],78)
        self.assertAlmostEqual(r['grid_import_plan_kw'],350);self.assertEqual(r['ev_served_kw'],88)
    def test_conservation_and_maximality_randomized(self):
        rng=np.random.default_rng(2026)
        for _ in range(500):
            soc=rng.uniform(20,95);b=rng.uniform(0,350);ev=rng.uniform(0,120);pv=rng.uniform(0,125)
            r=apply_first(decision(charge=rng.uniform(0,100)),State(soc),b,ev,pv,C)
            self.assertAlmostEqual(pv+r['grid_import_plan_kw']+r['battery_discharge_kw'],b+r['ev_served_kw']+r['battery_charge_kw']+r['grid_export_plan_kw'])
            dc=min(100,(soc*2-40)*.95/.25)
            self.assertAlmostEqual(r['ev_served_kw'],min(ev,88,max(0,350+pv+dc-b)))
            self.assertAlmostEqual(r['battery_energy_kwh'],soc*2+.25*(r['battery_charge_kw']*.95-r['battery_discharge_kw']/.95))
            self.assertLessEqual(r['grid_import_plan_kw'],350+1e-8)
            self.assertTrue(20-1e-8<=r['battery_soc_after_pct']<=95+1e-8)
    def test_impossible_building_blocks_execution(self):
        with self.assertRaises(PhysicalInfeasibleError):apply_first(decision(),State(20),351,80,0,C)
    def test_invalid_measurement(self):
        with self.assertRaises(ValueError):apply_first(decision(),State(50),100,float('nan'),0,C)
