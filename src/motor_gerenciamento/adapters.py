"""Thin read-only adapters to the actual frozen Motor 1 and Motor 2 APIs."""
import pandas as pd
from .state import ForecastInputs
def aligned_inputs(building,ev,solar,import_tariff=None,export_credit=None,measurements=None,provenance=None):
    a=pd.DatetimeIndex(pd.to_datetime(building.timestamp_previsto));b=pd.DatetimeIndex(pd.to_datetime(ev.timestamp_previsto))
    if len(a)!=48 or not a.equals(b):raise ValueError('Motor 1 and Motor 2 timestamps must match exactly (48).')
    for external in [solar,import_tariff,export_credit]:
        if isinstance(external,pd.Series) and not pd.DatetimeIndex(external.index).equals(a):raise ValueError('External forecast timestamps differ.')
    return ForecastInputs(a,building.consumo_previsto_kw.to_numpy(),ev.potencia_solicitada_prevista_kw.to_numpy(),ev.potencia_solicitada_alta_kw.to_numpy(),
        ev.probabilidade_fila.to_numpy(),solar,import_tariff,export_credit,measurements,provenance or {})
class FrozenForecastAdapters:
    def __init__(self):
        from motor_consumo.predict import MotorHibrido
        from motor_carregadores_v2.predict import MotorCarregadores
        self.building=MotorHibrido();self.ev=MotorCarregadores()
    def predict(self,building_history,ev_history,origin):
        a=self.building.predict(building_history,origin);b=self.ev.predict(ev_history,origin)
        if not a.timestamp_previsto.equals(b.timestamp_previsto):raise ValueError('Frozen predictions misaligned.')
        return a,b
