"""Mathematical tests: real HiGHS, independent physics guard, no mocked solves."""
import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from .config import Config,Battery,Inverter,EVSE,Circuit,from_manifest
from .mpc import optimize
from .guard import verify
from .balancer import allocate
from .state import SimulatedState

def cfg(batteries=0):
    return Config('TEST',8,2,[Battery('B'+str(i),10+5*i,.5,.2,.9,3,3,.95,.9,'I') for i in range(batteries)], [Inverter('I',10,12)],[EVSE('E',7)])
def solve(c,load=2,solar=0,demand=7,energy=None):
    b=np.broadcast_to(load,(48,)).copy();p=np.full((48,len(c.inverters)),solar,dtype=float);d=np.full((48,len(c.evses)),demand,dtype=float)
    r=optimize(c,energy or c.initial_energy(),b,p,d)
    return r,(b,p,d)

class Mathematics(unittest.TestCase):
    def check(self,c,load=2,solar=0,demand=7,energy=None):
        r,args=solve(c,load,solar,demand,energy);self.assertTrue(r['execution_allowed'],str(r))
        self.assertLess(r['verification']['max_balance_error_kw'],2e-5);self.assertLess(r['verification']['max_energy_error_kwh'],2e-5)
        json.dumps(r,allow_nan=False);return r
    def test_01_no_battery_priority(self):
        c=cfg();c.import_kw=3;r=self.check(c)
        # Objective locks allow 1e-5 kWh = 4e-5 kW over a 15-minute step.
        self.assertAlmostEqual(r['first_decision']['ev_served_kw'],1,delta=4.1e-5)
    def test_02_one_battery(self):self.check(cfg(1))
    def test_03_two_distinct_batteries_soc(self):
        c=cfg(2);r=self.check(c,energy={'B0':2.,'B1':12.})
        self.assertLess(r['first_decision']['batteries']['B0']['discharge_kw'],1e-5)
    def test_04_battery_unavailable(self):
        c=cfg(2);c.batteries[0].available=False;r=self.check(c,solar=9,demand=0)
        for row in r['plan']:
            self.assertAlmostEqual(row['batteries']['B0']['energy_after_kwh'],5,places=5)
    def test_05_soc_max_charge_limited(self):
        c=cfg(1);c.export_kw=0;r=self.check(c,load=0,solar=10,demand=0,energy={'B0':9.})
        self.assertAlmostEqual(r['first_decision']['solar_curtailed_kw'],10,places=5)
    def test_06_soc_min_discharge_limited(self):
        c=cfg(1);r=self.check(c,energy={'B0':2.})
        self.assertTrue(all(x['batteries']['B0']['discharge_kw']<1e-5 for x in r['plan']))
    def test_07_inverter_shared(self):
        c=cfg(2);c.inverters[0].ac_kw=4;r=self.check(c,solar=10,demand=0)
        for x in r['plan']:
            self.assertLessEqual(x['solar_used_kw']+sum(b['charge_kw']+b['discharge_kw'] for b in x['batteries'].values()),4.00002)
    def test_08_export_and_curtailment(self):
        r=self.check(cfg(),load=1,solar=12,demand=0)
        self.assertAlmostEqual(r['first_decision']['grid_export_kw'],2,places=5)
        self.assertAlmostEqual(r['first_decision']['solar_curtailed_kw'],9,places=5)
    def test_09_no_equipment(self):
        c=Config('EMPTY',5,0);r=self.check(c,load=3,solar=0,demand=0)
        self.assertEqual(r['first_decision']['evse_setpoints_kw'],{})
    def test_10_mandatory_infeasible(self):
        c=cfg();r,_=solve(c,load=20);self.assertFalse(r['execution_allowed']);self.assertEqual(r['status'],'infeasible');self.assertNotIn('first_decision',r)
    def test_11_no_artificial_cycles(self):
        c=cfg(2);r=self.check(c,load=np.resize([1,4,0,5],48),solar=5,demand=2)
        for x in r['plan']:
            ch=sum(v['charge_kw'] for v in x['batteries'].values());di=sum(v['discharge_kw'] for v in x['batteries'].values())
            self.assertFalse(ch>2e-5 and di>2e-5)
            self.assertFalse(x['grid_import_kw']>2e-5 and x['grid_export_kw']>2e-5)
            if ch>2e-5:self.assertLess(x['grid_import_kw'],2e-5)
    def test_12_invalid_nan(self):
        r,_=solve(cfg(),load=np.nan);self.assertFalse(r['execution_allowed'])
    def test_13_guard_detects_energy_creation(self):
        c=cfg(1);r,args=solve(c);self.assertTrue(r['execution_allowed']);r['plan'][2]['batteries']['B0']['energy_after_kwh']+=1
        with self.assertRaises(ValueError):verify(c,c.initial_energy(),*args,r['plan'])
    def test_14_grid_policy_explicit(self):
        c=cfg(1);c.policy='grid_allowed_lex_v3.0';self.check(c)
        c.policy='unknown';r,_=solve(c);self.assertFalse(r['execution_allowed'])
    def test_15_inverter_offline(self):
        c=cfg(1);c.inverters[0].available=False;r=self.check(c,solar=5)
        self.assertAlmostEqual(r['first_decision']['solar_used_kw'],0,places=5)
    def test_16_circuit_limit(self):
        c=cfg();c.evses=[EVSE('A',22),EVSE('B',22)];c.circuits=[Circuit('C',['A','B'],4)]
        r=self.check(c,demand=22);self.assertAlmostEqual(r['first_decision']['ev_served_kw'],4,delta=4.1e-5)
    def test_17_minimum_in_mpc(self):
        c=cfg();c.import_kw=3;c.evses[0].minimum_kw=2;r=self.check(c)
        self.assertAlmostEqual(r['first_decision']['ev_served_kw'],0,places=5)
    def test_18_load_balancer_fairness_vehicle_limits(self):
        es=[EVSE('A',22),EVSE('B',22),EVSE('C',22)];req={e.evse_id:dict(connected=True,requested_kw=22,vehicle_max_kw=7 if e.evse_id=='A' else 22) for e in es}
        r=allocate(es,req,27);self.assertEqual(r['setpoints_kw'],{'A':7.,'B':10.,'C':10.})
    def test_19_disconnected_offline(self):
        es=[EVSE('A',22),EVSE('B',22)];req={'A':dict(connected=False,requested_kw=22),'B':dict(connected=True,requested_kw=22,available=False)}
        self.assertEqual(allocate(es,req,44)['allocated_kw'],0)
    def test_20_minimum_and_rotation(self):
        es=[EVSE('A',7,3),EVSE('B',7,3)];req={e.evse_id:dict(connected=True,requested_kw=7) for e in es}
        a=allocate(es,req,4,cycle=0);b=allocate(es,req,4,cycle=1)
        self.assertAlmostEqual(a['allocated_kw'],4,places=5);self.assertNotEqual(a['suspended'],b['suspended'])
    def test_21_balancer_circuit(self):
        es=[EVSE('A',22),EVSE('B',22)];req={e.evse_id:dict(connected=True,requested_kw=22) for e in es}
        r=allocate(es,req,20,[Circuit('C',['A'],5)])
        self.assertEqual(r['setpoints_kw'],{'A':5.,'B':15.})
    def test_22_checkpoint_and_sequential_energy(self):
        c=cfg(2)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'energy.json';s=SimulatedState(c,path);t=pd.Timestamp('2025-10-01T00:00:00-03:00')
            for j in range(3):
                r,_=solve(c,energy=s.energy);self.assertTrue(r['execution_allowed']);s.commit(t+pd.Timedelta(minutes=j*15),r['first_decision'])
            saved=s.view();restored=SimulatedState(c,path);self.assertEqual(restored.view(),saved)
            c.station_id='OTHER'
            with self.assertRaises(ValueError):SimulatedState(c,path)
    def test_23_random_feasible_physics(self):
        rng=np.random.default_rng(42)
        for count in [0,1,2]:
            c=cfg(count);r,args=solve(c,load=rng.uniform(0,6,48),solar=3,demand=5)
            self.assertTrue(r['execution_allowed'],str(r));verify(c,c.initial_energy(),*args,r['plan'])

if __name__=='__main__':unittest.main(verbosity=2)
