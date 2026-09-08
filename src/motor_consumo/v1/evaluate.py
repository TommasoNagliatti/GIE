"""Baselines, avaliação temporal e teste de produção do Motor 1."""
if __package__ in (None,''):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from motor_consumo.v1.features import (SOURCE,MODELS,OUTPUT,STEP,HORIZONS,load_data,
    historical_features,horizon_features,split_masks,write_json)


def metrics(actual,predicted):
    y=np.asarray(actual,dtype=float).ravel(); p=np.asarray(predicted,dtype=float).ravel()
    if not (np.isfinite(y).all() and np.isfinite(p).all()):
        raise ValueError('Métricas receberam nulos ou infinitos.')
    err=np.abs(y-p)
    denominator=np.abs(y)+np.abs(p)
    return {'mae_kw':float(err.mean()),'rmse_kw':float(np.sqrt(np.mean((y-p)**2))),
            'wape_pct':float(100*err.sum()/np.abs(y).sum()) if np.abs(y).sum()>0 else None,
            'smape_pct':float(200*np.divide(err,denominator,out=np.zeros_like(err),where=denominator>0).mean()),
            'n':len(y)}


def baselines(data,h):
    y=data.consumo_predio_kw
    return {'persistencia':y,'dia_anterior':y.shift(96-h),'semana_anterior':y.shift(672-h)}


def baseline_metrics(data,partition='validation'):
    mask=split_masks(data,historical_features(data))[partition]
    rows=[]
    for h in HORIZONS:
        actual=data.consumo_predio_kw.shift(-h).loc[mask]
        for name,pred in baselines(data,h).items():
            rows.append({'partition':partition,'method':name,'horizon':h,'minutes':h*15,
                         **metrics(actual,pred.loc[mask])})
    return pd.DataFrame(rows)


def plots(predictions,score):
    import os
    cache=OUTPUT/'.matplotlib'
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(cache))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.style.use('seaborn-v0_8-whitegrid')
    folder=OUTPUT/'graficos'; folder.mkdir(exist_ok=True)
    test=score[score.partition=='test']
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    for name,sub in test.groupby('method'):
        axes[0].plot(sub.minutes/60,sub.mae_kw,label=name)
        axes[1].plot(sub.minutes/60,sub.wape_pct,label=name)
    for ax,label in zip(axes,['MAE (kW)','WAPE (%)']):
        ax.set(xlabel='Horizonte desde a última linha observada (h)',ylabel=label)
        ax.legend(fontsize=8)
    fig.suptitle('Motor 1 | erro por horizonte — teste em junho')
    fig.tight_layout(); fig.savefig(folder/'erro_por_horizonte.png',dpi=150); plt.close(fig)
    imp=pd.read_csv(OUTPUT/'feature_importance.csv')
    imp['normalized_gain']=imp.gain/imp.groupby('horizon').gain.transform('sum')
    ranked=imp.groupby('feature').normalized_gain.mean().sort_values().tail(18)
    fig,ax=plt.subplots(figsize=(11,7))
    ax.barh(ranked.index,ranked.values*100,color='#2166ac')
    ax.set(xlabel='Participação média do ganho nos 48 modelos (%)',title='Principais features | importância de treino, não causal')
    fig.tight_layout(); fig.savefig(folder/'importancia_features.png',dpi=150); plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(13,7),sharex=True)
    for ax,h in zip(axes,[1,24]):
        sub=predictions[(predictions.horizon==h)&(predictions.timestamp_previsto>='2026-06-08')&(predictions.timestamp_previsto<'2026-06-11')]
        ax.plot(sub.timestamp_previsto,sub.real_kw,label='Real',color='black',lw=1.4)
        ax.plot(sub.timestamp_previsto,sub.lightgbm,label='LightGBM',color='#2166ac',lw=1.2)
        ax.plot(sub.timestamp_previsto,sub.semana_anterior,label='Semana anterior',alpha=.55,lw=1)
        ax.set(ylabel='Consumo (kW)',title=f'Previsões sucessivas com horizonte fixo de +{h*15} min')
        ax.legend(fontsize=8)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %Hh'))
    fig.tight_layout(); fig.savefig(folder/'real_previsto_periodos_teste.png',dpi=150); plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,8))
    for ax,origin in zip(axes.flat,['2026-06-03 07:45','2026-06-10 13:45','2026-06-20 07:45','2026-06-29 17:45']):
        sub=predictions[predictions.timestamp_origem==pd.Timestamp(origin)].sort_values('horizon')
        ax.plot(sub.timestamp_previsto,sub.real_kw,label='Real',color='black')
        ax.plot(sub.timestamp_previsto,sub.lightgbm,label='LightGBM',color='#2166ac')
        ax.plot(sub.timestamp_previsto,sub.semana_anterior,label='Semana anterior',alpha=.55)
        ax.set(title=f'Emitida em {pd.Timestamp(origin)+STEP:%d/%m %H:%M}',ylabel='kW')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M')); ax.legend(fontsize=7)
    fig.suptitle('48 previsões de cada origem | horizonte completo de 12h')
    fig.tight_layout(); fig.savefig(folder/'previsoes_12h.png',dpi=150); plt.close(fig)


def evaluate(source=SOURCE):
    import lightgbm as lgb
    from motor_consumo.v1.predict import MotorConsumo
    data=load_data(source)
    metadata=json.loads((MODELS/'metadata.json').read_text(encoding='utf-8'))
    if hashlib.sha256(source.read_bytes()).hexdigest()!=metadata['source']['sha256']:
        raise ValueError('Fonte diferente da usada no treino. Avaliação cancelada.')
    base=historical_features(data); masks=split_masks(data,base)
    rows=[]; all_predictions={}; aggregated=[]
    for partition in ['validation','test']:
        frames=[]; mask=masks[partition]; index=data.index[mask]
        for h in HORIZONS:
            x=horizon_features(data,h,base)
            model=lgb.Booster(model_file=str(MODELS/f'horizon_{h:02d}.txt'))
            actual=data.consumo_predio_kw.shift(-h).loc[mask].to_numpy()
            predictions={name:v.loc[mask].to_numpy() for name,v in baselines(data,h).items()}
            predictions['lightgbm']=np.maximum(0,model.predict(x.loc[mask],num_threads=2))
            for name,pred in predictions.items():
                rows.append({'partition':partition,'method':name,'horizon':h,'minutes':h*15,**metrics(actual,pred)})
            frames.append(pd.DataFrame({'timestamp_origem':index,'timestamp_previsto':index+h*STEP,
                                        'horizon':h,'real_kw':actual,**predictions}))
        joined=pd.concat(frames,ignore_index=True)
        joined.to_csv(OUTPUT/f'predictions_{partition}.csv',index=False,float_format='%.6f')
        all_predictions[partition]=joined
        for name in ['persistencia','dia_anterior','semana_anterior','lightgbm']:
            aggregated.append({'partition':partition,'method':name,**metrics(joined.real_kw,joined[name])})
    score=pd.DataFrame(rows); score.to_csv(OUTPUT/'metrics_by_horizon.csv',index=False)
    totals=pd.DataFrame(aggregated); totals.to_csv(OUTPUT/'metrics_overall.csv',index=False)
    selected=score[(score.partition=='test')&score.horizon.isin([1,4,12,24,48])]
    selected.to_csv(OUTPUT/'metrics_selected_horizons.csv',index=False)
    plots(all_predictions['test'],score)
    origin=pd.Timestamp('2026-06-15 07:45')
    past=data.loc[:origin].copy()  # Physically exclude the future before inference.
    engine=MotorConsumo()
    prediction=engine.predict(past,origin)
    actual=data.consumo_predio_kw.reindex(prediction.timestamp_previsto).to_numpy()
    production=prediction.copy(); production['real_kw']=actual
    production['erro_absoluto_kw']=np.abs(actual-prediction.consumo_previsto_kw)
    prediction.to_csv(OUTPUT/'exemplo_predict_48.csv',index=False,float_format='%.6f')
    production.to_csv(OUTPUT/'teste_producao.csv',index=False,float_format='%.6f')
    batch=all_predictions['test'].loc[all_predictions['test'].timestamp_origem==origin].sort_values('horizon')
    np.testing.assert_allclose(prediction.consumo_previsto_kw,batch.lightgbm,rtol=0,atol=1e-9)
    poisoned=data.copy()
    poisoned.loc[poisoned.index>origin,:]=np.nan
    guarded=engine.predict(poisoned,origin)
    pd.testing.assert_frame_equal(prediction,guarded)
    production_audit={'last_observed_interval':str(origin),'issued_at':str(origin+STEP),
                      'history_rows':len(past),'future_hidden':True,'rows_predicted':len(prediction),
                      'batch_inference_match':True,'future_poison_invariance':True,
                      **metrics(actual,prediction.consumo_previsto_kw)}
    write_json(OUTPUT/'production_validation.json',production_audit)
    write_json(OUTPUT/'evaluation_summary.json',{'overall':aggregated,'production_test':production_audit,
        'test_wape_best_method':totals[totals.partition=='test'].sort_values('wape_pct').iloc[0]['method'],
        'no_test_tuning':True,'negative_prediction_floor_applied':True})
    write_report(metadata,score,totals,production_audit,prediction)
    print(totals.to_string(index=False))
    print('\nTeste de produção:'); print(production_audit)


def write_report(metadata,score,totals,production_audit,prediction):
    lines=['# Goodwe — Motor 1: primeira avaliação', '',
           'Pipeline local concluído: 48 LightGBM diretos, um por horizonte de 15 a 720 minutos. Os modelos são um único motor de inferência.', '',
           f'Fonte oficial: `{metadata["source"]["source_path"]}`. SHA-256: `{metadata["source"]["sha256"]}`. CSV original preservado.', '',
           '**Resultado principal:** o baseline semanal supera o LightGBM em junho. Não houve ajustes de hiperparâmetros após observar o teste. Em maio, o LightGBM havia melhorado o baseline semanal.', '',
           '## Dados e features', '',
           '| Partição | Origens por horizonte | Primeiro registro de origem | Último registro de origem |', '|---|---:|---|---|']
    for name,info in metadata['splits'].items():
        lines.append(f'| {name} | {info["origins"]} | {info["first_origin"]} | {info["last_origin"]} |')
    lines += ['',f'{metadata["feature_count"]} features por horizonte: consumo atual; lags 15m, 30m, 1h, 2h, 3h, 6h, 12h, 24h e 7 dias; média/mínimo/máximo/desvio em janelas de 1h, 3h, 6h e 24h; temperatura e umidade atuais, lags e médias passadas; calendário atual e alvo com ciclos seno/cosseno; consumo histórico do horário alvo no dia/semana anterior.', '',
              'Os sete primeiros dias servem de contexto. As últimas 48 origens de cada partição são excluídas para que nenhum target atravesse a fronteira. Contexto de meses anteriores é permitido, pois já era conhecido.', '',
              '## Métricas agregadas', '',
              'MAE e RMSE em kW. WAPE = 100 × soma dos erros absolutos / soma do consumo real; não é média de erros percentuais por linha. sMAPE é também salvo nos CSVs. O agregado utiliza todos os pares origem–horizonte; não representa 135.936 medições independentes.', '',
              '| Partição | Método | MAE kW | RMSE kW | WAPE % |', '|---|---|---:|---:|---:|']
    for r in totals.itertuples():
        lines.append(f'| {r.partition} | {r.method} | {r.mae_kw:.3f} | {r.rmse_kw:.3f} | {r.wape_pct:.3f} |')
    lines += ['', '## Horizontes selecionados — junho', '', '| Minutos | Método | MAE kW | RMSE kW | WAPE % |', '|---:|---|---:|---:|---:|']
    for r in score[(score.partition=='test')&score.horizon.isin([1,4,12,24,48])].itertuples():
        lines.append(f'| {r.minutes} | {r.method} | {r.mae_kw:.3f} | {r.rmse_kw:.3f} | {r.wape_pct:.3f} |')
    lines += ['', '## Produção simulada', '',
              f'Última linha observada: {production_audit["last_observed_interval"]}; emissão: {production_audit["issued_at"]}. Foram ocultados todos os registros posteriores antes de chamar predict. Saída: 48 intervalos. As previsões coincidiram com o lote; substituir o futuro por nulos também não alterou a saída.', '',
              f'Este exemplo teve MAE {production_audit["mae_kw"]:.3f} kW, RMSE {production_audit["rmse_kw"]:.3f} kW e WAPE {production_audit["wape_pct"]:.3f}%. É um caso de erro alto e não foi substituído por outro mais favorável.', '',
              '```csv',prediction.head(6).to_csv(index=False,float_format='%.6f').strip(),'```', '',
              'Arquivo completo: `exemplo_predict_48.csv`; comparação real: `teste_producao.csv`.', '',
              '## Interpretação e limites', '',
              'A importância por ganho é fortemente concentrada no consumo do horário alvo da semana anterior. Isso combina com a rotina semanal repetida do dataset sintético; não estabelece causalidade. A diferença entre maio e junho demonstra que a vantagem na validação não garantiu generalização. Não foram usados clima futuro, interpolação de lacunas, embaralhamento temporal nem recalibração sobre junho.', '',
              'A primeira versão é funcional, mas o LightGBM ainda não demonstrou superioridade ao melhor baseline neste teste. O dataset tem apenas seis meses e representa um único prédio sintético. As próximas revisões devem preservar uma nova avaliação temporal independente.', '',
              '## Gráficos', '',
              '![Erro por horizonte](graficos/erro_por_horizonte.png)', '',
              '![Real e previsto](graficos/real_previsto_periodos_teste.png)', '',
              '![Importância](graficos/importancia_features.png)', '',
              '![Previsões de 12h](graficos/previsoes_12h.png)', '']
    (OUTPUT/'relatorio_motor1.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=SOURCE)
    parser.add_argument('--baselines-only',action='store_true')
    args=parser.parse_args()
    if args.baselines_only:
        OUTPUT.mkdir(parents=True,exist_ok=True)
        result=baseline_metrics(load_data(args.data))
        result.to_csv(OUTPUT/'baselines_validation_before_training.csv',index=False)
        print(result.groupby('method')[['mae_kw','rmse_kw','wape_pct']].mean().to_string())
    else:
        evaluate(args.data)
