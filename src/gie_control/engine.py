"""One core, two input sources. No telemetry source is silently substituted."""
from .profile import ROOT,load_profile
from .outputs import standardize
from load_balancer.state import BalancerState

class GIEEngine:
    def __init__(self,root=None,components=None):
        self.root=root or ROOT
        self.profile,self.config=load_profile(self.root)
        self.components=components
        self.balancer_state=None

    def initialize_models(self):
        if self.components is None:
            from gie_runtime.adapters import Components
            from integracoes.solar.config import SolarConfig
            from integracoes.solar.forecast import SolarForecaster
            from integracoes.weather.open_meteo import OpenMeteoProvider
            from integracoes.weather.cache import ForecastCache
            from motor_consumo.predict import MotorHibrido
            from motor_carregadores_v2.predict import MotorCarregadores
            from pathlib import Path
            solar=SolarForecaster(OpenMeteoProvider(),ForecastCache(Path(self.root)/'runtime_cache/weather.json'),
                 SolarConfig(installed_kwp=self.profile['solar_dc_kwp'],inverter_ac_kw=self.profile['solar_ac_kw']))
            self.components=Components(MotorHibrido(),MotorCarregadores(),solar)
        return self

    def run_cycle(self,decision_time,history,current,mode='NORMAL'):
        from motor_gerenciamento_v2.runtime_adapter import run_cycle
        if mode not in ('NORMAL','SIMULATION'):raise ValueError('Use presentation/manual controls for demo modes')
        self.initialize_models()
        result=run_cycle(decision_time,history,current,self.components,config=self.config,balancer_state=self.balancer_state)
        if result['management']['execution_allowed']:
            self.balancer_state=BalancerState(**result['load_balancer']['next_state'])
        return standardize(result,mode,{'input_source':'caller telemetry','forecasts':'frozen models and supplied solar provider'})
