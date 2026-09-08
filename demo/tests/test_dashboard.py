import unittest,socket
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[2]
class DashboardTests(unittest.TestCase):
    def test_replay_controls_offline(self):
        with patch.object(socket,'create_connection',side_effect=AssertionError('offline')):
            at=AppTest.from_file(str(ROOT/'demo/app.py'),default_timeout=30).run()
            self.assertEqual(len(at.exception),0)
            at.button(key='next').click().run();self.assertEqual(at.session_state['replay'].index,1)
            at.button(key='reset').click().run();self.assertEqual(at.session_state['replay'].index,0)
            self.assertEqual(len(at.exception),0)
    def test_live_does_not_run_on_open(self):
        with patch('subprocess.run',side_effect=AssertionError('unexpected execution')):
            at=AppTest.from_file(str(ROOT/'demo/app.py'),default_timeout=30).run()
            at.radio[0].set_value('Live Demo').run()
            self.assertEqual(len(at.exception),0);self.assertIsNone(at.session_state['live_frame'])
    def test_all_scenarios_render(self):
        at=AppTest.from_file(str(ROOT/'demo/app.py'),default_timeout=30).run()
        for _ in range(7):
            at.button(key='next').click().run();self.assertEqual(len(at.exception),0)
if __name__=='__main__':unittest.main()
