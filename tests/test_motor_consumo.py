"""Testes causais: futuro alterado, limites de partição e lags conhecidos."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import unittest
import numpy as np
import pandas as pd
from motor_consumo.v1.features import (STEP,HORIZONS,load_data,historical_features,horizon_features,
                                    split_masks,validate_frame,targets,target_name)
from motor_consumo.v1.evaluate import baselines,metrics


class CausalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_data()

    def test_future_cannot_change_features(self):
        origin=pd.Timestamp('2026-05-12 09:00')
        changed=self.data.copy()
        changed.loc[changed.index>origin,:]=1e9
        past=self.data.loc[:origin]
        bases=[historical_features(d) for d in [self.data,changed,past]]
        for h in HORIZONS:
            expected=horizon_features(self.data,h,bases[0]).loc[origin]
            pd.testing.assert_series_equal(expected,horizon_features(changed,h,bases[1]).loc[origin])
            pd.testing.assert_series_equal(expected,horizon_features(past,h,bases[2]).loc[origin])

    def test_no_target_crosses_partition(self):
        base=historical_features(self.data)
        masks=split_masks(self.data,base)
        for part,end in [('train','2026-05-01'),('validation','2026-06-01'),('test','2026-07-01')]:
            origins=self.data.index[masks[part]]
            self.assertTrue((origins+48*STEP<pd.Timestamp(end)).all())
        self.assertEqual([int(masks[n].sum()) for n in ['train','validation','test']],[10800,2928,2832])

    def test_target_and_seasonal_baseline_alignment(self):
        origin=pd.Timestamp('2026-04-20 09:00'); y=targets(self.data)
        for h in HORIZONS:
            self.assertEqual(y.loc[origin,target_name(h)],self.data.loc[origin+h*STEP,'consumo_predio_kw'])
            b=baselines(self.data,h)
            for name,days in [('dia_anterior',1),('semana_anterior',7)]:
                lookup=origin+h*STEP-pd.Timedelta(days=days)
                self.assertLessEqual(lookup,origin)
                self.assertEqual(b[name].loc[origin],self.data.loc[lookup,'consumo_predio_kw'])

    def test_bad_input_fails_without_repair(self):
        for bad in [self.data.drop(self.data.index[100]),pd.concat([self.data,self.data.iloc[[-1]]])]:
            with self.assertRaises(ValueError): validate_frame(bad)
        bad=self.data.copy(); bad.iloc[50,0]=np.nan
        with self.assertRaises(ValueError): validate_frame(bad)

    def test_zero_safe_percentage_metric(self):
        m=metrics([0,10],[0,12])
        self.assertEqual(m['mae_kw'],1)
        self.assertEqual(m['wape_pct'],20)
        self.assertTrue(np.isfinite(m['smape_pct']))


if __name__=='__main__': unittest.main()
