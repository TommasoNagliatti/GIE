import sys, unittest, random
from pathlib import Path
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from load_balancer import run_balancer, EVSEState, Config

T = '2026-08-01T12:00:00'
def devices(n=4):
    return [EVSEState(f'EVSE{i+1}', i < n, connected_since='2026-08-01T08:00:00' if i < n else None) for i in range(4)]
def powers(r):
    return [r[f'evse_{i}_kw'] for i in range(1, 5)]

class LoadBalancerTests(unittest.TestCase):
    def run_case(self, block, ds=None, **kwargs):
        return run_balancer(block, devices() if ds is None else ds, T, **kwargs)
    def test_no_car(self):
        r,_=self.run_case(88,devices(0));self.assertEqual(powers(r),[0]*4)
    def test_one_car_88(self):
        r,_=self.run_case(88,devices(1));self.assertEqual(powers(r),[22,0,0,0])
    def test_four_cars_88(self):
        r,_=self.run_case(88);self.assertEqual(powers(r),[22]*4)
    def test_four_cars_44(self):
        r,_=self.run_case(44);self.assertEqual(powers(r),[11]*4)
    def test_three_cars_54(self):
        r,_=self.run_case(54,devices(3));self.assertEqual(powers(r),[18,18,18,0])
    def test_vehicle_cap_redistribution(self):
        ds=devices(3);ds[1]=replace(ds[1],vehicle_max_kw=11)
        r,_=self.run_case(54,ds);self.assertEqual(powers(r),[21.5,11,21.5,0])
    def test_fault_zero(self):
        ds=devices();ds[1]=replace(ds[1],state='fault')
        r,_=self.run_case(60,ds);self.assertEqual(powers(r),[20,0,20,20])
        self.assertIn('EVSE_FAULT',[e['code'] for e in r['events']])
    def test_zero_block(self):
        r,_=self.run_case(0);self.assertEqual(powers(r),[0]*4)
        self.assertNotIn('EV_BLOCK_FULLY_ALLOCATED',[e['code'] for e in r['events']])
    def test_changing_block_immediate_safe_reduction(self):
        state=None
        for block in [88,44,3,0,60,88]:
            r,state=self.run_case(block,previous=state)
            self.assertLessEqual(sum(powers(r)),block)
            for p in powers(r):self.assertAlmostEqual(p,block/4)
    def test_reported_evse_cap(self):
        ds=devices();ds[0]=replace(ds[0],max_power_kw=5)
        r,_=self.run_case(88,ds);self.assertEqual(powers(r),[5,22,22,22])
    def test_no_evse_exceeds_22(self):
        ds=[replace(e,max_power_kw=100,vehicle_max_kw=50) for e in devices()]
        r,_=self.run_case(88,ds);self.assertEqual(powers(r),[22]*4)
    def test_fairness_not_id_or_input_order(self):
        ds=devices();ds[0]=replace(ds[0],connected_since='2026-08-01T07:00:00')
        r,_=self.run_case(37,ds)
        other,_=self.run_case(37,list(reversed(ds)))
        self.assertEqual(powers(r),powers(other));self.assertEqual(powers(r),[9.25]*4)
    def test_identical_inputs_stable(self):
        state=None;last=None
        for _ in range(30):
            r,state=self.run_case(49,previous=state)
            if last is not None:self.assertEqual(powers(last),powers(r))
            last=r
    def test_randomized_limits_utilization_and_max_min(self):
        rng=random.Random(20260906)
        for _ in range(2000):
            block=rng.uniform(0,88)
            ds=[replace(e,max_power_kw=rng.uniform(0,30),vehicle_max_kw=rng.uniform(0,30),connected=rng.choice([True,False])) for e in devices()]
            r,_=self.run_case(block,ds)
            caps=[min(22,e.max_power_kw,e.vehicle_max_kw) if e.connected else 0 for e in ds]
            ps=powers(r)
            self.assertLessEqual(sum(ps),block)
            self.assertAlmostEqual(sum(ps),min(block,sum(caps)),places=10)
            for p,cap in zip(ps,caps):self.assertTrue(0<=p<=cap)
            unsaturated=[p for p,cap in zip(ps,caps) if cap-p>1e-8]
            if unsaturated:self.assertLess(max(unsaturated)-min(unsaturated),1e-8)
    def test_transition_events_not_repeated(self):
        ds=devices(1);r,state=self.run_case(10,ds)
        self.assertEqual(sum(e['code']=='EVSE_CONNECTED' for e in r['events']),1)
        r,state=self.run_case(10,ds,previous=state)
        self.assertNotIn('EVSE_CONNECTED',[e['code'] for e in r['events']])
        r,state=self.run_case(10,devices(0),previous=state)
        self.assertIn('EVSE_DISCONNECTED',[e['code'] for e in r['events']])
    def test_fault_event_transition(self):
        ds=devices();ds[0]=replace(ds[0],state='fault')
        r,state=self.run_case(88,ds)
        r,_=self.run_case(88,ds,previous=state)
        self.assertNotIn('EVSE_FAULT',[e['code'] for e in r['events']])
    def test_suspended_offline_and_zero_acceptance(self):
        ds=devices();ds[0]=replace(ds[0],state='suspended');ds[1]=replace(ds[1],state='offline');ds[2]=replace(ds[2],vehicle_max_kw=0)
        r,_=self.run_case(88,ds);self.assertEqual(powers(r),[0,0,0,22])
    def test_minimum_configuration(self):
        config=Config(minimum_kw={f'EVSE{i}':6 for i in range(1,5)})
        for block in [0,5,6,11,12,18,25,88]:
            r,_=self.run_case(block,config=config)
            self.assertLessEqual(sum(powers(r)),block)
            self.assertTrue(all(p==0 or p>=6 for p in powers(r)))
    def test_minimum_equal_ties_rotate_not_fixed_id(self):
        config=Config(minimum_kw={f'EVSE{i}':6 for i in range(1,5)})
        state=None;totals=[0]*4
        for _ in range(4):
            r,state=self.run_case(6,config=config,previous=state)
            totals=[a+b for a,b in zip(totals,powers(r))]
        self.assertEqual(totals,[6]*4)
    def test_arrival_only_admission_tiebreak(self):
        ds=devices();ds[2]=replace(ds[2],connected_since='2026-08-01T07:00:00')
        config=Config(minimum_kw={f'EVSE{i}':6 for i in range(1,5)})
        r,_=self.run_case(6,ds,config=config);self.assertEqual(powers(r),[0,0,6,0])
    def test_cap_below_minimum_not_forced(self):
        ds=devices(1);ds[0]=replace(ds[0],vehicle_max_kw=4)
        r,_=self.run_case(88,ds,config=Config(minimum_kw={'EVSE1':6}))
        self.assertEqual(powers(r),[0]*4)
    def test_invalid_blocks(self):
        for block in [-1,89,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):self.run_case(block)
    def test_invalid_devices(self):
        for ds in [devices()[:3],devices()+devices()[:1],[devices()[0]]*4]:
            with self.assertRaises(ValueError):self.run_case(88,ds)
        for value in [-1,float('nan'),float('inf')]:
            ds=devices();ds[0]=replace(ds[0],vehicle_max_kw=value)
            with self.assertRaises(ValueError):self.run_case(88,ds)
    def test_future_session_rejected(self):
        ds=devices();ds[0]=replace(ds[0],connected_since='2026-08-02')
        with self.assertRaises(ValueError):self.run_case(88,ds)

if __name__=='__main__':unittest.main()
