"""Avaliação da seleção em maio e diagnóstico secundário de junho, sem seleção."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib
import json
import os
import numpy as np
import pandas as pd
import lightgbm as lgb
from motor_consumo.features import *
from motor_consumo.v1.evaluate import metrics
from motor_consumo.predict import MotorHibrido


def apply_selection(frame,selection):
    frame=frame.copy()
    frame['hibrido']=np.nan
    for row in selection:
        mask=frame.horizon==row['horizon']
        frame.loc[mask,'hibrido']=frame.loc[mask,row['method']]
    if frame.hibrido.isna().any(): raise ValueError('Seletor incompleto.')
    return frame


def evaluate():
    metadata=json.loads((MODELS/'metadata.json').read_text(encoding='utf-8'))
    selector_bytes=(MODELS/'selector.json').read_bytes()
    if hashlib.sha256(selector_bytes).hexdigest()!=metadata['selector_sha256']:
        raise ValueError('Seletor alterado após o treino.')
    selector=json.loads(selector_bytes); selection=selector['horizons']
    data=load_data(SOURCE)
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=metadata['source_sha256']:
        raise ValueError('Fonte de dados alterada.')
    base=residual_base(data); v1base=historical_features(data)
    mask=masks_for(data,base)['diagnostic_june']
    frames=[]
    # June is first used here, after the May selector has been saved and hashed.
    for h in HORIZONS:
        model=lgb.Booster(model_file=str(MODELS/f'residual_{h:02d}.txt'))
        v1=lgb.Booster(model_file=str(V1_MODELS/f'horizon_{h:02d}.txt'))
        weekly=weekly_baseline(data,h).loc[mask].to_numpy()
        residual=model.predict(residual_features(data,h,base).loc[mask],num_threads=2)
        frames.append(pd.DataFrame({'timestamp_origem':data.index[mask],
            'timestamp_previsto':data.index[mask]+h*STEP,'horizon':h,
            'real_kw':data.consumo_predio_kw.shift(-h).loc[mask].to_numpy(),
            'persistencia':data.consumo_predio_kw.loc[mask].to_numpy(),
            'semana_anterior':weekly,
            'lightgbm_v1':np.maximum(0,v1.predict(horizon_features(data,h,v1base).loc[mask],num_threads=2)),
            'residual_v2':np.maximum(0,weekly+residual)}))
    diagnostic=apply_selection(pd.concat(frames,ignore_index=True),selection)
    diagnostic.to_csv(OUTPUT/'predictions_diagnostic_june.csv',index=False,float_format='%.9f')
    validation=apply_selection(pd.read_csv(OUTPUT/'predictions_validation.csv',parse_dates=['timestamp_origem','timestamp_previsto']),selection)
    validation.to_csv(OUTPUT/'predictions_validation_hybrid.csv',index=False,float_format='%.9f')
    scores=[]; overall=[]
    for partition,frame in [('validation',validation),('diagnostic_june',diagnostic)]:
        for method in METHODS+['hibrido']:
            overall.append({'partition':partition,'method':method,**metrics(frame.real_kw,frame[method])})
            for h,sub in frame.groupby('horizon'):
                scores.append({'partition':partition,'method':method,'horizon':int(h),'minutes':int(h)*15,
                               **metrics(sub.real_kw,sub[method])})
    score=pd.DataFrame(scores); totals=pd.DataFrame(overall)
    score.to_csv(OUTPUT/'metrics_by_horizon.csv',index=False)
    totals.to_csv(OUTPUT/'metrics_overall.csv',index=False)
    counts={method:sum(r['method']==method for r in selection) for method in METHODS}
    ranges=[]
    for row in selection:
        if ranges and ranges[-1]['method']==row['method']:
            ranges[-1]['end_minutes']=row['minutes']
        else:
            ranges.append({'start_minutes':row['minutes'],'end_minutes':row['minutes'],'method':row['method']})
    write_json(OUTPUT/'selection_summary.json',{'counts':counts,'consecutive_ranges':ranges})
    # Production test uses only past observations, before revealing truth.
    origin=pd.Timestamp('2026-06-15 07:45')
    engine=MotorHibrido(); forecast=engine.predict(data.loc[:origin].copy(),origin)
    forecast.to_csv(OUTPUT/'exemplo_hibrido_48.csv',index=False,float_format='%.9f')
    batch=diagnostic[diagnostic.timestamp_origem==origin].sort_values('horizon')
    np.testing.assert_allclose(forecast.consumo_previsto_kw,batch.hibrido,atol=1e-8,rtol=0)
    poison=data.copy(); poison.loc[poison.index>origin,:]=np.nan
    pd.testing.assert_frame_equal(forecast,engine.predict(poison,origin))
    example=forecast.copy(); example['real_kw']=batch.real_kw.to_numpy()
    example['metodo']=[r['method'] for r in selection]
    example['v1_kw']=batch.lightgbm_v1.to_numpy()
    example.to_csv(OUTPUT/'production_diagnostic.csv',index=False,float_format='%.9f')
    production={'origin':str(origin),'issued_at':str(origin+STEP),'predictions':48,
                'future_hidden':True,'future_poison_invariance':True,'batch_matches_inference':True,
                'role':'secondary diagnostic, not independent test',**metrics(example.real_kw,example.consumo_previsto_kw)}
    write_json(OUTPUT/'production_validation.json',production)
    # Verify no selector mutation occurred during diagnostic evaluation.
    if (MODELS/'selector.json').read_bytes()!=selector_bytes: raise ValueError('Seletor foi modificado.')
    plot_results(score,diagnostic,example)
    report(metadata,totals,score,counts,ranges,production,forecast)
    print(totals.to_string(index=False)); print('Seleção:',counts); print('Faixas:',ranges)
    print('Produção:',production)


def plot_results(score,diagnostic,example):
    cache=OUTPUT/'.matplotlib'; cache.mkdir(exist_ok=True)
    os.environ['MPLCONFIGDIR']=str(cache)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    folder=OUTPUT/'graficos'; folder.mkdir(exist_ok=True)
    plt.style.use('seaborn-v0_8-whitegrid')
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    for ax,partition,title in zip(axes,['validation','diagnostic_june'],['Maio — validação usada para seleção','Junho — diagnóstico secundário']):
        for method in METHODS+['hibrido']:
            sub=score[(score.partition==partition)&(score.method==method)]
            ax.plot(sub.minutes/60,sub.mae_kw,label=method,ls='--' if method=='hibrido' else '-',lw=2.3 if method=='hibrido' else 1.2)
        ax.set(title=title,xlabel='Horizonte (h)',ylabel='MAE (kW)'); ax.legend(fontsize=7)
    fig.suptitle('Motor 1 V2 | sem teste final independente disponível')
    fig.tight_layout(); fig.savefig(folder/'mae_horizontes.png',dpi=150); plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,5))
    ax.plot(example.timestamp_previsto,example.real_kw,label='Real',color='black')
    ax.plot(example.timestamp_previsto,example.consumo_previsto_kw,label='Híbrido V2')
    ax.plot(example.timestamp_previsto,example.v1_kw,label='V1 absoluto',alpha=.7)
    ax.set(title='12 horas emitidas em 15/06 às 08h | diagnóstico secundário',ylabel='kW')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M')); ax.legend()
    fig.tight_layout(); fig.savefig(folder/'exemplo_12h.png',dpi=150); plt.close(fig)


def report(meta,totals,score,counts,ranges,production,forecast):
    lines=['# Goodwe Motor 1 V2 — híbrido por horizonte','',
           '**Junho é apenas diagnóstico secundário. Nenhum teste final independente está disponível nesta etapa.**','',
           'Os 48 modelos absolutos V1 foram preservados. A V2 treinou 48 LightGBM para o resíduo y(t+h)−y(t+h−7 dias). O seletor minimiza MAE em maio entre persistência, semanal, V1 e residual V2; junho não é aceito pela função de seleção.','',
           f'Features por modelo residual: {meta["feature_count"]}. Origens: {meta["train_origins"]} no treino, {meta["validation_origins"]} na validação, 2.832 no diagnóstico. V1 e candidatos foram comparados nas mesmas origens de maio e junho.','',
           'A V2 acrescenta diferença e razão atual/semana anterior, diferença atual/dia anterior, tendências de 15min/1h/3h/6h, média e desvio das correções semanais em janelas de 1h/3h/6h/24h, diferenças semanais e tendência de 1h de temperatura/umidade.','',
           '## Métricas agregadas','', '| Partição | Método | MAE kW | RMSE kW | WAPE % |','|---|---|---:|---:|---:|']
    for r in totals.itertuples(): lines.append(f'| {r.partition} | {r.method} | {r.mae_kw:.3f} | {r.rmse_kw:.3f} | {r.wape_pct:.3f} |')
    lines+=['','WAPE = 100 × soma dos erros absolutos / soma do consumo real. Agregados incluem todos os pares origem–horizonte, sobrepostos no tempo. Métricas por horizonte: `metrics_by_horizon.csv`.','',
            '## Seleção exclusivamente em maio','','| Método | Horizontes |','|---|---:|']
    for name,count in counts.items(): lines.append(f'| {name} | {count} |')
    lines+=['','| De (min) | Até (min) | Método |','|---:|---:|---|']
    for row in ranges: lines.append(f'| {row["start_minutes"]} | {row["end_minutes"]} | {row["method"]} |')
    lines+=['','O desenho permite um método diferente a cada horizonte. Não se força diversidade caso um candidato vença todos. Em empate exato a ordem é persistência, semanal, V1, residual.','',
            '## Horizontes selecionados — diagnóstico de junho','','| Minutos | Método | MAE kW | RMSE kW | WAPE % |','|---:|---|---:|---:|---:|']
    for r in score[(score.partition=='diagnostic_june')&score.horizon.isin([1,4,12,24,48])].itertuples():
        lines.append(f'| {r.minutes} | {r.method} | {r.mae_kw:.3f} | {r.rmse_kw:.3f} | {r.wape_pct:.3f} |')
    lines+=['','## Exemplo de produção','',
            f'Origem {production["origin"]}, disponível/emissão em {production["issued_at"]}. Foram fornecidas somente linhas até a origem. MAE {production["mae_kw"]:.3f} kW, RMSE {production["rmse_kw"]:.3f} kW, WAPE {production["wape_pct"]:.3f}%.','',
            '```csv',forecast.head(6).to_csv(index=False,float_format='%.6f').strip(),'```','',
            'As 48 previsões coincidiram com o lote. Substituir os dados futuros por nulos não alterou a saída. Resultado completo: `exemplo_hibrido_48.csv`.','',
            '## Limitações','',
            'Maio é reutilizado para early stopping e seleção; o desempenho do híbrido nesse conjunto tem otimismo de seleção. Junho já influenciou o desenho desta V2 e não permite alegar generalização independente. Um novo período não observado será necessário. A formulação, hiperparâmetros e seletor não foram ajustados usando os resultados diagnósticos de junho nesta execução.','',
            '![MAE](graficos/mae_horizontes.png)','','![Previsão completa](graficos/exemplo_12h.png)','']
    (OUTPUT/'relatorio_v2.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__': evaluate()
