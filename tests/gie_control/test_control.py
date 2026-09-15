import unittest,json,sys,socket
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from gie_control import GIEControl,standardize,GIEEngine
from gie_control.scenarios import validate_physics,validate_behavior,EVENTS
from gie_control.profile import load_profile

SCENES=json.loads((ROOT/'src/gie_control/assets/scenes.json').read_text(encoding='utf-8'))['scenes']
class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.c=GIEControl(clock=self.clock);self.c.set_mode('PRESENTATION')
    def test_numeric_lossless(self):
        raw=deepcopy(SCENES[5]['result']);r=standardize(raw)
        for k in ('management','forecasts','flows','events','health','load_balancer'):self.assertEqual(raw[k],r[k])
        self.assertEqual(r['numeric_state']['battery_charge_kw'],raw['management']['battery_charge_kw'])
    def test_deterministic_messages(self):
        r=SCENES[5]['result'];a=standardize(r);b=standardize(r)
        self.assertEqual(a['messages'],b['messages']);self.assertEqual(a['visual_state'],b['visual_state'])
        for msg in a['messages']:
            for key,v in msg['numeric_context'].items():
                if key in a['numeric_state']:self.assertEqual(v,a['numeric_state'][key])
        self.assertIn('SOLAR_SURPLUS',a['reason_codes'])
    def test_messages_no_false_redistribution(self):
        msg=SCENES[12]['result']['primary_message']
        self.assertNotIn('foi redistribuída',msg['text'])
        self.assertEqual(msg['numeric_context']['allocated_kw'],0)
    def test_blocked_unknown_not_zero(self):
        r=deepcopy(SCENES[0]['result']);r['management']={'execution_allowed':False};r['status']='blocked';r['load_balancer']=None
        x=standardize(r);self.assertIsNone(x['numeric_state']['battery_charge_kw']);self.assertEqual(x['visual_state']['battery_flow'],'unknown')
        self.assertEqual(x['primary_message']['severity'],'critical')
    def test_json(self):json.dumps(self.c.get_state(),allow_nan=False)
    def test_next_previous(self):
        self.c.next_scene();self.assertEqual(self.c.get_presentation_state()['scene_number'],2)
        self.c.previous_scene();self.assertEqual(self.c.index,0)
    def test_pause_resume(self):
        self.c.start_presentation();self.clock.now=4;self.c.pause_presentation();self.clock.now=100;self.c.tick();self.assertEqual(self.c.index,0)
        self.c.resume_presentation();self.clock.now=105;self.c.tick();self.assertEqual(self.c.index,0)
        self.clock.now=106;self.c.tick();self.assertEqual(self.c.index,1)
    def test_autoplay_bounded(self):
        self.c.start_presentation();self.clock.now=1000;self.c.tick();self.assertEqual(self.c.index,1)
        self.c.tick();self.assertEqual(self.c.index,1)
    def test_speed(self):
        self.c.start_presentation();self.clock.now=3;self.c.set_presentation_interval(5);self.clock.now=7;self.c.tick();self.assertEqual(self.c.index,0)
        self.clock.now=8;self.c.tick();self.assertEqual(self.c.index,1)
    def test_loop(self):
        self.c.set_scene('16');self.c.set_loop(True);self.c.next_scene();self.assertEqual(self.c.index,0)
    def test_stop_at_end(self):
        self.c.set_scene('16');self.c.start_presentation();self.clock.now=10;self.c.tick();self.assertFalse(self.c.playing);self.assertEqual(self.c.index,15)
    def test_reset(self):
        self.c.set_scene('12');self.c.start_presentation();self.c.stop_presentation();self.assertEqual(self.c.index,0);self.assertFalse(self.c.playing)
    def test_modes(self):
        for mode in ('NORMAL','SIMULATION','MANUAL_DEMO','PRESENTATION'):self.assertEqual(self.c.set_mode(mode),mode)
        with self.assertRaises(ValueError):self.c.set_mode('LIVE')
    def test_event_guard(self):
        with self.assertRaises(ValueError):self.c.trigger_demo_event('EV_PEAK')
    def test_invalid_controls(self):
        with self.assertRaises(ValueError):self.c.set_scene('99')
        with self.assertRaises(ValueError):self.c.set_presentation_interval(0)
        with self.assertRaises(ValueError):self.c.set_loop('true')
    def test_no_mutation(self):
        s=self.c.get_state();s['numeric_state']['solar_kw']=9999
        self.assertNotEqual(self.c.get_state()['numeric_state']['solar_kw'],9999)
    def test_offline_all_scenes(self):
        with patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')):
            for s in SCENES:self.c.set_scene(s['id']);json.dumps(self.c.get_state())
    def test_history_bounded(self):
        for _ in range(110):self.c.set_scene('01')
        self.assertEqual(len(self.c.message_history),100)
    def test_profile(self):
        p,c=load_profile();self.assertEqual(p['solar_ac_kw'],c.pv_ac_max_kw);self.assertEqual(c.reserve_pct,0)
    def test_critical_event(self):
        r=deepcopy(SCENES[0]['result']);r['events'].insert(0,{'code':'SENSOR_FAILURE','severity':'critical'})
        self.assertEqual(standardize(r)['primary_message']['severity'],'critical')
    def test_manual_reset(self):
        self.c.set_mode('MANUAL_DEMO');r=self.c.reset_demo();self.assertEqual(r['mode'],'MANUAL_DEMO');validate_physics(r)
    def test_infeasible_manual_no_stale_command(self):
        self.c.set_mode('MANUAL_DEMO');self.c.trigger_demo_event('BUILDING_PEAK');self.c.trigger_demo_event('SOLAR_DROP')
        r=self.c.trigger_demo_event('SOC_LOW');self.assertFalse(r['execution_allowed'])
        self.assertEqual(r['visual_state']['battery_flow'],'unknown');self.assertEqual(r['numeric_state']['evse_setpoints_kw'],[None]*4)
    def test_multiple_faults(self):
        self.c.set_mode('MANUAL_DEMO');self.c.trigger_demo_event('FAULT_EVSE1');r=self.c.trigger_demo_event('FAULT_EVSE2')
        self.assertTrue(r['visual_state']['evse_1_fault']);self.assertTrue(r['visual_state']['evse_2_fault'])
        r=self.c.trigger_demo_event('RECOVER_EVSES');self.assertFalse(any(r['visual_state'][f'evse_{i}_fault'] for i in range(1,5)))

def scene_test(scene):
    def test(self):
        self.assertTrue(validate_physics(scene['result']));self.assertTrue(validate_behavior(scene['result'],scene['expected_behaviors']))
    return test
for scene in SCENES:setattr(ControlTests,'test_scene_'+scene['id'],scene_test(scene))

def event_test(code):
    def test(self):
        self.c.set_mode('MANUAL_DEMO')
        with patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')):
            r=self.c.trigger_demo_event(code)
        self.assertTrue(validate_physics(r));self.assertEqual(r['mode'],'MANUAL_DEMO')
        if code.startswith('FAULT_'):self.assertEqual(r['numeric_state']['evse_setpoints_kw'][int(code[-1])-1],0)
    return test
for code in EVENTS:setattr(ControlTests,'test_event_'+code.lower(),event_test(code))
if __name__=='__main__':unittest.main()
