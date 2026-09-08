import sys,unittest,tempfile,json
from pathlib import Path
from dataclasses import replace
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from integracoes.weather.models import WeatherSite,horizon,COLUMNS,STEP
from integracoes.weather.open_meteo import OpenMeteoProvider,VARIABLES,UNITS
from integracoes.weather.cache import ForecastCache
from integracoes.solar.forecast import SolarForecaster,irradiance_to_power
from integracoes.solar.config import SolarConfig
from integracoes.solar.adapter import to_motor3

START=pd.Timestamp('2026-09-07 08:00',tz='America/Sao_Paulo')
def fixture(start=START):
    ix=horizon(start,97)
    return dict(timezone='America/Sao_Paulo',utc_offset_seconds=-10800,
        minutely_15_units=dict(time='unixtime',**dict(zip(VARIABLES,UNITS))),
        minutely_15=dict(time=[int(t.timestamp()) for t in ix],global_tilted_irradiance=list(range(97)),
            shortwave_radiation=[100.]*97,direct_normal_irradiance=[50.]*97,
            temperature_2m=[20.]*97,relative_humidity_2m=[60.]*97,cloud_cover=[30.]*97))

class SolarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=ForecastCache(Path(self.tmp.name)/'cache.json')
        self.now=START
    def service(self,raw=None,failure=None):
        raw=fixture() if raw is None else raw
        def transport(url,timeout):
            self.assertEqual(timeout,10)
            if failure is not None:raise failure
            return raw
        p=OpenMeteoProvider(transport=transport,clock=lambda:self.now)
        return SolarForecaster(p,self.cache,clock=lambda:self.now)
    def test_valid_api_response(self):
        r=self.service().forecast(START)
        self.assertEqual(r.source,'open_meteo');self.assertFalse(r.stale)
        self.assertEqual(r.data.shape,(48,7))
    def test_exact_48(self):self.assertEqual(len(self.service().forecast(START).data),48)
    def test_exact_15_minutes(self):
        ix=self.service().forecast(START).data.index
        self.assertTrue((ix[1:]-ix[:-1]==STEP).all())
    def test_sao_paulo_timezone(self):self.assertEqual(str(self.service().forecast(START).data.index.tz),'America/Sao_Paulo')
    def test_night_zero(self):
        raw=fixture();raw['minutely_15']['global_tilted_irradiance']=[0.]*97
        self.assertTrue((self.service(raw).forecast(START).data.solar_previsto_kw==0).all())
    def test_nonnegative_power(self):self.assertEqual(irradiance_to_power([-100],SolarConfig())[0],0)
    def test_inverter_cap(self):self.assertEqual(irradiance_to_power([2000],SolarConfig())[0],125)
    def test_formula_and_configurable_pr(self):
        self.assertAlmostEqual(irradiance_to_power([1000],SolarConfig())[0],123)
        self.assertAlmostEqual(irradiance_to_power([1000],SolarConfig(performance_ratio=.7))[0],105)
    def test_outage_recent_cache_covers_next_cycle(self):
        self.service().forecast(START)
        self.now+=STEP
        r=self.service(failure=OSError('API unavailable')).forecast(START+STEP)
        self.assertEqual(r.source,'cache');self.assertTrue(r.stale)
        self.assertEqual(r.data.index[0],START+STEP)
        self.assertEqual(r.data.global_tilted_irradiance_wm2.iloc[0],2)
    def test_outage_no_cache_zero(self):
        r=self.service(failure=OSError('API unavailable')).forecast(START)
        self.assertEqual(r.source,'fallback');self.assertTrue(r.stale)
        self.assertTrue((r.data.solar_previsto_kw==0).all())
        self.assertTrue(r.data[COLUMNS].isna().all().all())
        self.assertIsNone(r.to_dict()['records'][0]['temperature_c'])
    def test_expired_cache_zero(self):
        self.service().forecast(START);self.now+=pd.Timedelta(hours=4)
        self.assertEqual(self.service(failure=OSError()).forecast(self.now).source,'fallback')
    def test_cache_missing_horizon_zero(self):
        self.service().forecast(START)
        self.assertEqual(self.service(failure=OSError()).forecast(START+pd.Timedelta(days=2)).source,'fallback')
    def test_corrupt_cache_zero(self):
        self.cache.path.write_text('{bad')
        self.assertEqual(self.service(failure=OSError()).forecast(START).source,'fallback')
    def test_cache_other_orientation_not_reused(self):
        self.service().forecast(START)
        service=self.service(failure=OSError());service.config=replace(service.config,site=WeatherSite(azimuth=0))
        self.assertEqual(service.forecast(START).source,'fallback')
    def test_exact_motor3_alignment(self):
        r=self.service().forecast(START)
        ix=pd.date_range('2026-09-07 08:00',periods=48,freq='15min')
        series=to_motor3(r,ix)
        self.assertTrue(series.index.equals(ix));self.assertEqual(series.index[-1],pd.Timestamp('2026-09-07 19:45'))
    def test_radiation_end_label_conversion(self):
        r=self.service().forecast(START)
        self.assertEqual(r.data.global_tilted_irradiance_wm2.iloc[0],1)
        self.assertEqual(r.data.global_tilted_irradiance_wm2.iloc[-1],48)
        self.assertEqual(r.data.index[0],START)
    def test_instant_weather_not_shifted(self):
        raw=fixture();raw['minutely_15']['temperature_2m']=list(range(97))
        r=self.service(raw).forecast(START)
        self.assertEqual(r.data.temperature_c.iloc[0],0)
        self.assertEqual(r.data.temperature_c.iloc[-1],47)
    def test_shifted_motor3_rejected(self):
        r=self.service().forecast(START)
        with self.assertRaises(ValueError):to_motor3(r,horizon(START+STEP).tz_localize(None))
    def test_unaligned_decision_rejected(self):
        with self.assertRaises(ValueError):self.service().forecast(START+pd.Timedelta(minutes=1))
    def test_utc_decision_same_instant(self):
        self.assertTrue(self.service().forecast(START.tz_convert('UTC')).data.index.equals(horizon(START)))
    def test_midnight_crossing(self):
        t=START.replace(hour=23,minute=45)
        r=self.service(fixture(t)).forecast(t)
        self.assertTrue(r.data.index.equals(horizon(t)))
    def test_missing_field_fallback(self):
        raw=fixture();del raw['minutely_15']['cloud_cover']
        self.assertEqual(self.service(raw).forecast(START).source,'fallback')
    def test_missing_field_preserves_valid_cache(self):
        self.service().forecast(START);before=self.cache.path.read_bytes()
        raw=fixture();del raw['minutely_15']['global_tilted_irradiance']
        self.assertEqual(self.service(raw).forecast(START).source,'cache')
        self.assertEqual(before,self.cache.path.read_bytes())
    def test_timeout_network_fallback(self):
        r=self.service(failure=TimeoutError('network timeout')).forecast(START)
        self.assertEqual(r.source,'fallback');self.assertIn('TimeoutError',r.metadata['diagnostics'][0])
    def test_wrong_api_timezone_rejected(self):
        raw=fixture();raw['timezone']='UTC'
        self.assertEqual(self.service(raw).forecast(START).source,'fallback')
    def test_missing_duplicate_null_api_rows(self):
        for mode in ('missing','duplicate','null'):
            raw=fixture()
            if mode=='missing':raw['minutely_15']['time'].pop()
            if mode=='duplicate':raw['minutely_15']['time'][3]=raw['minutely_15']['time'][2]
            if mode=='null':raw['minutely_15']['temperature_2m'][2]=None
            self.assertEqual(self.service(raw).forecast(START).source,'fallback')
    def test_cache_write_failure_does_not_discard_api(self):
        from unittest.mock import patch
        with patch.object(self.cache,'save',side_effect=OSError('read only')):
            self.assertEqual(self.service().forecast(START).source,'open_meteo')
    def test_adapter_unchanged_motor3_accepts_series(self):
        from motor_gerenciamento.adapters import aligned_inputs
        from motor_gerenciamento.config import Config
        from motor_gerenciamento.state import State
        ix=horizon(START).tz_localize(None)
        a=pd.DataFrame(dict(timestamp_previsto=ix,consumo_previsto_kw=np.full(48,100.)))
        b=pd.DataFrame(dict(timestamp_previsto=ix,potencia_solicitada_prevista_kw=np.full(48,20.),potencia_solicitada_alta_kw=np.full(48,40.),probabilidade_fila=np.zeros(48)))
        solar=to_motor3(self.service().forecast(START),ix)
        inputs=aligned_inputs(a,b,solar,np.ones(48),np.zeros(48)).validated(Config(),State(50))
        np.testing.assert_array_equal(inputs.solar_kw,solar.to_numpy())
    def test_api_parameters_orientation_and_97_endpoints(self):
        p=OpenMeteoProvider().parameters(START,WeatherSite())
        self.assertEqual(p['tilt'],23);self.assertEqual(p['azimuth'],180)
        self.assertEqual(p['start_minutely_15'],'2026-09-07T08:00')
        self.assertEqual(p['end_minutely_15'],'2026-09-08T08:00')
        self.assertEqual(p['minutely_15'],','.join(VARIABLES))

if __name__=='__main__':unittest.main()
