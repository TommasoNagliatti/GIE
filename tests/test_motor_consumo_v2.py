import sys
sys.dont_write_bytecode=True
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import unittest
import numpy as np
import pandas as pd
from motor_consumo.features import *


class V2Causality(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data=load_data()

    def test_residual_reconstructs_target(self):
        t=pd.Timestamp('2026-04-20 09:00')
        for h in HORIZONS:
            self.assertAlmostEqual(residual_target(self.data,h).loc[t]+weekly_baseline(self.data,h).loc[t],self.data.loc[t+h*STEP,'consumo_predio_kw'])

    def test_future_cannot_change_residual_features(self):
        t=pd.Timestamp('2026-05-12 09:00')
        changed=self.data.copy(); changed.loc[changed.index>t,:]=1e9
        past=self.data.loc[:t].iloc[-MIN_HISTORY:]
        bases=[residual_base(d) for d in [self.data,changed,past]]
        for h in HORIZONS:
            original=residual_features(self.data,h,bases[0]).loc[t]
            pd.testing.assert_series_equal(original,residual_features(changed,h,bases[1]).loc[t])
            pd.testing.assert_series_equal(original,residual_features(past,h,bases[2]).loc[t])

    def test_split_boundaries(self):
        masks=masks_for(self.data,residual_base(self.data))
        for name,end in [('train','2026-05-01'),('validation','2026-06-01'),('diagnostic_june','2026-07-01')]:
            self.assertTrue((self.data.index[masks[name]]+48*STEP<pd.Timestamp(end)).all())
        self.assertEqual([int(masks[n].sum()) for n in ['train','validation','diagnostic_june']],[10705,2928,2832])

    def test_selector_rejects_diagnostic_and_is_horizon_specific(self):
        scores=pd.DataFrame([{'partition':'validation','horizon':h,'method':m,
                              'mae_kw':float((i-h)%4)} for h in HORIZONS for i,m in enumerate(METHODS)])
        selected=select_methods(scores)
        self.assertEqual([r['method'] for r in selected],[METHODS[h%4] for h in HORIZONS])
        scores['partition']='diagnostic_june'
        with self.assertRaises(ValueError): select_methods(scores)


if __name__=='__main__': unittest.main()
