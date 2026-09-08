"""Validate isolated adapter and save a real Open-Meteo forecast; no GIE loop."""
import sys,os,json,io,unittest,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from integracoes.weather.models import ZONE
from integracoes.weather.open_meteo import OpenMeteoProvider
from integracoes.weather.cache import ForecastCache
from integracoes.solar.forecast import SolarForecaster
from integracoes.solar.adapter import to_motor3

def main():
    out=ROOT/'outputs/integracoes/solar_v1'
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests/integracoes'))
    stream=io.StringIO();tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (out/'test_results.txt').write_text(stream.getvalue(),encoding='utf-8')
    if not tests.wasSuccessful():raise RuntimeError('Tests failed.')
    called=pd.Timestamp.now(tz=ZONE)
    # Only this demonstration chooses the next quarter. Production receives
    # the exact Motor 3 horizon start, never rounds it internally.
    start=called.ceil('15min')
    provider=OpenMeteoProvider()
    cache=ForecastCache(out/'.cache/last_valid_weather.json')
    result=SolarForecaster(provider,cache).forecast(start)
    expected=pd.date_range(start.tz_localize(None),periods=48,freq='15min')
    series=to_motor3(result,expected)
    assert series.index.equals(expected) and len(series)==48
    result.data.to_csv(out/'previsao_solar_12h.csv',float_format='%.6f')
    (out/'previsao_solar_12h.json').write_text(json.dumps(result.to_dict(),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (out/'api_request.json').write_text(json.dumps(dict(called_at=called.isoformat(),url=provider.last_url,parameters=provider.parameters(start,SolarForecaster(provider,cache).config.site)),indent=2),encoding='utf-8')
    if provider.last_response is not None:
        (out/'open_meteo_raw.json').write_text(json.dumps(provider.last_response,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    series.to_csv(out/'motor3_solar_adapter.csv',index_label='timestamp')
    def fail(url,timeout):raise TimeoutError('deliberate timeout for fallback validation')
    offline=OpenMeteoProvider(transport=fail)
    cached=SolarForecaster(offline,cache).forecast(start)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        fallback=SolarForecaster(offline,ForecastCache(Path(tmp)/'missing.json')).forecast(start)
    (out/'fallback_examples.json').write_text(json.dumps(dict(with_cache=cached.to_dict(),without_cache=fallback.to_dict()),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.environ['MPLCONFIGDIR']=str(out/'.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    data=result.data
    for kind in ('gti_solar','geracao_solar'):
        fig,ax=plt.subplots(figsize=(12,4.8))
        if kind=='gti_solar':
            ax.plot(data.index,data.global_tilted_irradiance_wm2,color='darkorange',label='GTI')
            ax.set_ylabel('GTI (W/m²)',color='darkorange')
            other=ax.twinx();other.plot(data.index,data.solar_previsto_kw,color='steelblue',label='Solar')
            other.set_ylabel('Solar prevista (kW)',color='steelblue');other.set_ylim(0,135)
        else:
            ax.step(data.index,data.solar_previsto_kw,where='post',color='steelblue',label='Previsão solar')
            ax.fill_between(data.index,0,data.solar_previsto_kw,step='post',alpha=.2)
            ax.axhline(125,color='red',ls='--',label='Limite AC 125 kW');ax.set_ylabel('Potência (kW)');ax.set_ylim(0,135);ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M',tz=data.index.tz))
        ax.set_xlabel('Início do intervalo — America/Sao_Paulo');ax.grid(alpha=.2)
        ax.set_title(f'Previsão solar V1 | fonte: {result.source} | PR do protótipo: 0,82')
        fig.autofmt_xdate();fig.tight_layout();fig.savefig(out/(kind+'.png'),dpi=150);plt.close(fig)
    gti=data.global_tilted_irradiance_wm2
    summary=dict(called_at=called.isoformat(),source=result.source,stale=result.stale,
                 first_timestamp=data.index[0].isoformat(),last_timestamp=data.index[-1].isoformat(),records=len(data),
                 gti_min_wm2=None if gti.isna().all() else float(gti.min()),gti_max_wm2=None if gti.isna().all() else float(gti.max()),
                 solar_peak_kw=float(data.solar_previsto_kw.max()),positive_intervals=int((data.solar_previsto_kw>0).sum()),
                 tests_passed=tests.testsRun,motor3_alignment_verified=True,
                 fallback_with_cache_source=cached.source,fallback_without_cache_source=fallback.source,
                 diagnostics=result.metadata['diagnostics'])
    protected=json.loads((out/'preservation_before.json').read_text())
    changed=[p for p,h in protected.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    summary.update(protected_files_checked=len(protected),protected_files_changed=changed)
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,indent=2,ensure_ascii=False),flush=True)
    print(data[['global_tilted_irradiance_wm2','solar_previsto_kw']].to_string(),flush=True)

if __name__=='__main__':main()
