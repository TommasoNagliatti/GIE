import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[2]
class DashboardTests(unittest.TestCase):
 def test_profiles(self):
  a=AppTest.from_file(str(ROOT/"demo/high_autonomy_v2/app.py"),default_timeout=30).run()
  self.assertEqual(len(a.exception),0);self.assertEqual(a.radio[0].value,"High Autonomy V2")
  a.number_input[0].set_value(96).run();self.assertEqual(len(a.exception),0)
  self.assertIn("0.00 kWh",[x.value for x in a.metric])
  a.radio[0].set_value("Grid Connected V1").run();self.assertEqual(len(a.exception),0)
  self.assertIn("2214.78 kWh",[x.value for x in a.metric])
 def test_controls(self):
  a=AppTest.from_file(str(ROOT/"demo/high_autonomy_v2/app.py"),default_timeout=30).run()
  a.button[2].click().run();self.assertEqual(a.number_input[0].value,2)
  a.button[3].click().run();self.assertEqual(a.number_input[0].value,1)
  self.assertEqual(len(a.exception),0)
if __name__=="__main__":unittest.main()
