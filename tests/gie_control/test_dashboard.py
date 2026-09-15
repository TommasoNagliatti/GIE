import unittest,sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
class PresentationDashboardTests(unittest.TestCase):
    def app(self):
        a=AppTest.from_file(str(ROOT/'demo/high_autonomy_v2/app.py'),default_timeout=45).run()
        a.radio[1].set_value('Presentation').run();self.assertFalse(a.exception);return a
    def test_scene_controls(self):
        a=self.app();a.button(key='p_next').click().run();self.assertEqual(a.session_state.gie_control.index,1)
        a.button(key='p_prev').click().run();self.assertEqual(a.session_state.gie_control.index,0)
        a.button(key='p_start').click().run();self.assertTrue(a.session_state.gie_control.playing)
        a.button(key='p_pause').click().run();self.assertFalse(a.session_state.gie_control.playing)
        a.button(key='p_reset').click().run();self.assertEqual(a.session_state.gie_control.index,0);self.assertFalse(a.exception)
    def test_speed_loop(self):
        a=self.app();a.selectbox(key='presentation_interval').set_value(5).run();a.checkbox(key='presentation_loop').check().run()
        self.assertEqual(a.session_state.gie_control.interval,5);self.assertTrue(a.session_state.gie_control.loop)
    def test_manual(self):
        a=self.app();a.radio[1].set_value('Manual Demo').run();a.button(key='manual_FAULT_EVSE3').click().run()
        self.assertFalse(a.exception);self.assertTrue(a.session_state.gie_control.get_state()['visual_state']['evse_3_fault'])
    def test_all_scene_rendering(self):
        a=self.app()
        for _ in range(15):a.button(key='p_next').click().run();self.assertFalse(a.exception)
        self.assertEqual(a.session_state.gie_control.index,15)
if __name__=='__main__':unittest.main()
