import sys,unittest,json
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from gie_runtime import run_gie_cycle,History,CurrentState,Components
from integracoes.solar.models import SolarForecast
from integracoes.weather.models import horizon
from load_balancer import EVSEState,Config as LBConfig
from motor_gerenciamento.config import Config
from motor_gerenciamento.optimizer import optimize
from motor_gerenciamento.state import ForecastInputs,State
from motor_gerenciamento.dispatch import apply_first

T=pd.Timestamp('2026-09-07 10:00')
class Engine:
    def __init__(self,kind,b=100,ev=20,q=40):self.kind=kind;self.b=b;self.ev=ev;self.q=q;self.shift=0;self.error=False;self.last_history=None
    def predict(self,history,origin):
        self.last_history=history
        if self.error:raise RuntimeError('deliberate engine failure')
        ix=pd.date_range(origin+pd.Timedelta(minutes=15+self.shift),periods=48,freq='15min')
        if self.kind==1:return pd.DataFrame(dict(timestamp_previsto=ix,consumo_previsto_kw=np.full(48,self.b)))
        return pd.DataFrame(dict(timestamp_previsto=ix,potencia_solicitada_prevista_kw=np.full(48,self.ev),potencia_solicitada_alta_kw=np.full(48,self.q),
            energia_solicitada_prevista_kwh=np.full(48,self.ev*.25),carregadores_ocupados_previstos=np.full(48,2),
            carros_chegando_previstos=np.ones(48),carros_na_fila_previstos=np.zeros(48),probabilidade_fila=np.full(48,.2)))
class Solar:
    def __init__(self,power=0,source='open_meteo'):self.power=power;self.source=source
    def forecast(self,start):return SolarForecast(pd.DataFrame({'solar_previsto_kw':np.full(48,self.power)},index=horizon(start)),self.source,self.source!='open_meteo',{'diagnostics':[]})

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        ix=pd.date_range(T-pd.Timedelta(days=30),T-pd.Timedelta(minutes=15),freq='15min')
        self.history=History(pd.DataFrame({'value':0},index=ix),pd.DataFrame({'value':0},index=ix))
        self.current=CurrentState(T,100,44,0,50,[EVSEState(f'EVSE{i}',True,vehicle_max_kw=11,connected_since=T-pd.Timedelta(hours=1)) for i in range(1,5)])
        self.components=Components(Engine(1),Engine(2),Solar())
    def cycle(self):return run_gie_cycle(T,self.history,self.current,self.components)
    def check(self,r):
        self.assertIn(r['status'],['ok','degraded'],r['events'])
        self.assertEqual(len(r['forecasts']['records']),48);self.assertEqual(len(r['management']['plan']),48)
        mg=r['management'];lb=r['load_balancer'];row=mg['first_decision']
        self.assertEqual(lb['ev_block_limit_kw'],mg['ev_block_limit_kw'])
        self.assertLessEqual(lb['allocated_total_kw'],mg['ev_block_limit_kw']+1e-8)
        self.assertAlmostEqual(lb['allocated_total_kw'],sum(lb[f'evse_{i}_kw'] for i in range(1,5)))
        self.assertLess(mg['power_balance_error_kw'],1e-8)
        self.assertNotIn('grid_to_battery_kw',r['flows'])
        for p in mg['plan']:
            self.assertLessEqual(p['battery_charge_kw'],max(0,p['solar_disponivel_kw']-p['building_kw']-p['ev_expected_kw'])+1e-6)
        self.assertEqual(r['forecasts']['records'][0]['timestamp'],T.isoformat())
        self.assertEqual(mg['applied_step'],0)
        json.dumps(r,allow_nan=False)
    def test_complete_valid_cycle(self):
        r=self.cycle();self.check(r)
        self.assertEqual(r['status'],'ok')
        for f,p in zip(r['forecasts']['records'],r['management']['plan']):
            self.assertEqual(f['building_kw'],p['building_kw']);self.assertEqual(f['solar_previsto_kw'],p['solar_disponivel_kw'])
            self.assertEqual(f['potencia_solicitada_prevista_kw'],p['ev_expected_kw'])
    def test_misaligned_engine(self):
        self.components.motor2.shift=15;r=self.cycle()
        self.assertEqual(r['status'],'blocked');self.assertEqual(r['health']['alignment']['status'],'error')
        self.assertFalse(r['management']['execution_allowed'])
    def test_solar_fallback(self):
        self.components.solar=Solar(0,'fallback');r=self.cycle();self.check(r)
        self.assertEqual(r['status'],'degraded');self.assertEqual(r['health']['solar']['source'],'fallback')
    def test_motor1_error(self):
        self.components.motor1.error=True;r=self.cycle();self.assertEqual(r['status'],'blocked');self.assertEqual(r['health']['motor1']['status'],'error')
    def test_motor2_error(self):
        self.components.motor2.error=True;r=self.cycle();self.assertEqual(r['status'],'blocked');self.assertEqual(r['health']['motor2']['status'],'error')
    def test_solver_unavailable(self):
        def broken(*a,**kw):raise RuntimeError('solver unavailable')
        self.components.solver=broken;r=self.cycle();self.check(r)
        self.assertEqual(r['status'],'degraded');self.assertEqual(r['health']['motor3']['solver_status'],'fallback')
    def test_evse_fault(self):
        self.current.evses[0]=replace(self.current.evses[0],state='fault')
        r=self.cycle();self.check(r);self.assertEqual(r['load_balancer']['evse_1_kw'],0)
        self.assertEqual(r['health']['load_balancer']['status'],'degraded')
        self.assertEqual(r['management']['current_ev_unserved_total_kw'],11)
    def test_minimum_battery(self):
        self.current.battery_soc_pct=20;r=self.cycle();self.check(r)
        self.assertEqual(r['management']['battery_charge_kw'],0);self.assertEqual(r['management']['battery_discharge_kw'],0)
    def test_maximum_battery(self):
        self.current.battery_soc_pct=95;self.current.solar_kw=125;self.current.building_kw=10;self.current.ev_demand_kw=10
        self.components.motor1.b=10;self.components.motor2.ev=10;self.components.solar=Solar(125)
        r=self.cycle();self.check(r);self.assertEqual(r['management']['battery_charge_kw'],0)
        self.assertAlmostEqual(r['management']['grid_export_plan_kw'],105)
    def test_solar_surplus_charges(self):
        self.current.solar_kw=125;self.current.building_kw=10;self.current.ev_demand_kw=10
        self.components.motor1.b=10;self.components.motor2.ev=10;self.components.solar=Solar(125)
        r=self.cycle();self.check(r);self.assertGreater(r['management']['battery_charge_kw'],0)
        self.assertEqual(r['management']['grid_import_plan_kw'],0)
    def test_actual_ev_above_forecast(self):
        r=self.cycle();self.check(r);self.assertEqual(r['management']['first_decision']['ev_served_kw'],44)
        self.assertIn('EV_DEMAND_ABOVE_FORECAST',[e['code'] for e in r['events']])
    def test_json_complete(self):
        r=self.cycle();self.check(r);loaded=json.loads(json.dumps(r,allow_nan=False))
        for k in ['gie_version','decision_time','status','current_state','forecasts','management','load_balancer','flows','events','health']:self.assertIn(k,loaded)
        self.assertNotIn('tariff',json.dumps(r));self.assertNotIn('credit',json.dumps(r))
    def test_future_history_is_hidden(self):
        future=pd.DataFrame({'value':[999]},index=[T]);self.history.building=pd.concat([self.history.building,future])
        self.check(self.cycle());self.assertLess(self.components.motor1.last_history.index.max(),T)
    def test_bad_current_timestamp(self):
        self.current.timestamp=T-pd.Timedelta(minutes=15)
        r=self.cycle();self.assertEqual(r['status'],'blocked');self.assertEqual(r['health']['validation']['status'],'error')
    def test_timestamps_off_quarter_hour(self):
        r=run_gie_cycle(T+pd.Timedelta(minutes=1),self.history,self.current,self.components)
        self.assertEqual(r['status'],'blocked')
    def test_actual_surplus_missing_cancels_charge(self):
        self.components.solar=Solar(125);self.components.motor1.b=10;self.components.motor2.ev=10
        self.current.solar_kw=0
        r=self.cycle();self.check(r);self.assertEqual(r['management']['battery_charge_kw'],0)
    def test_impossible_building_blocks(self):
        self.current.building_kw=500;self.current.battery_soc_pct=20
        r=self.cycle();self.assertEqual(r['status'],'blocked');self.assertFalse(r['management']['execution_allowed'])
    def test_legacy_prices_do_not_change_plan(self):
        ix=horizon(T).tz_localize(None);a=lambda x:np.full(48,x)
        p=ForecastInputs(ix,a(100),a(20),a(40),a(.2),a(0))
        x=optimize(p,State(50))
        p2=ForecastInputs(ix,a(100),a(20),a(40),a(.2),a(0),a(100),a(10))
        y=optimize(p2,State(50))
        self.assertEqual(x['plan'],y['plan']);self.assertEqual(x['objective_value'],y['objective_value'])

if __name__=='__main__':unittest.main()
