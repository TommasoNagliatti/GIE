"""Phase 3–5 checks with Phase 5's evidence writer redirected to this delivery."""
import sys,unittest
from gie_multistation.registry import ROOT
import gie_provisioning.test_provisioning as phase5

def main():
    destination=ROOT/'reports/panel/v1/regression_outputs'
    (destination/'reports/provisioning/v1').mkdir(parents=True,exist_ok=True)
    phase5.ROOT=destination  # This test module uses ROOT only to write its evidence JSON.
    suite=unittest.defaultTestLoader.loadTestsFromNames(['gie_multistation.test_isolation','gie_energy_v3.test_math','gie_energy_v3.test_runtime','gie_provisioning.test_provisioning'])
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
if __name__=='__main__':sys.exit(main())
