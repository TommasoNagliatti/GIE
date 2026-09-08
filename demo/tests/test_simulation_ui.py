import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[2]
class SimulationUITests(unittest.TestCase):
    def app(self):
        at=AppTest.from_file(str(ROOT/"demo/app.py"),default_timeout=40).run()
        at.radio[0].set_value("Simulation Mode").run();return at
    def test_open_no_execution(self):
        with patch("subprocess.run",side_effect=AssertionError("No implicit core call")):
            at=self.app();self.assertEqual(len(at.exception),0);self.assertIsNone(at.session_state["sim_state"])
    def test_speed_pause_reset(self):
        at=self.app();at.selectbox[0].select("1 min real = 2 h simuladas").run();self.assertEqual(at.session_state["sim_clock"].interval,7.5)
        at.button(key="sim_pause").click().run();self.assertFalse(at.session_state["sim_clock"].playing)
        old=at.session_state["sim_folder"];at.button(key="sim_reset").click().run();self.assertNotEqual(at.session_state["sim_folder"],old)
        self.assertEqual(len(at.exception),0)
    def test_real_step(self):
        at=self.app();at.button(key="sim_next").click().run();self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state["sim_state"]["index"],1)
        self.assertEqual(at.session_state["sim_state"]["last_frame"]["cycle"]["status"],"ok")
if __name__=="__main__":unittest.main()
