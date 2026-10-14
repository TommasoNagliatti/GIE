"""Reuse the original suite runner, redirecting evidence to Phase 5 only."""
from gie_energy_v3 import regression
from gie_multistation.registry import ROOT

if __name__=='__main__':
    regression.OUT=ROOT/'reports/provisioning/v1'
    raise SystemExit(regression.main())
