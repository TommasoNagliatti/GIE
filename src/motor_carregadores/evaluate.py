"""Avaliação única de junho após congelamento; não treina ou seleciona."""
import sys,os
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_carregadores.features import *
from motor_carregadores.metrics import regression,classification
from motor_carregadores.predict import MotorCarregadores
def check_preserved():
    for name in ['preservation_before.json','freeze_manifest.json']:
        manifest=json.loads((OUTPUT/name).read_text(encoding='utf-8'))
        changed=[p for p,h in manifest.items() if digest(ROOT/p)!=h]
        if changed:raise RuntimeError('Arquivo congelado alterado: '+str(changed))
    return {'motor1_and_data_unchanged':True,'motor2_frozen_unchanged':True}
def evaluate():
    if (OUTPUT/'evaluation_completed.json').exists():raise RuntimeError('Junho já avaliado; não executar novamente.')
    preserved=check_preserved()
    engine=MotorCarregadores();meta=engine.meta;config=json.loads((MODELS/'config.json').read_text())
    if digest(SOURCE)!=meta['source_sha256']:raise ValueError('Fonte alterada.')
    data=load_data();x,y,b,info=make_long(data,'test')
    assert info.timestamp_previsto.min()>=pd.Timestamp('2026-06-01') and info.timestamp_previsto.max()<pd.Timestamp('2026-07-01')
    pred={n:m.predict(x[meta['features']],num_threads=2) for n,m in engine.models.items()}
    pred['power']=np.clip(b[:,3]+pred['power'],0,88)
    for name in ['occupancy','arrivals','queue']:pred[name]=np.clip(pred[name],0,LIMITS[name])
    rows=[];hrows=[]
    candidates={n:b[:,i] for i,n in enumerate(['persistencia','dia_anterior','semana_anterior','media_4semanas'])}
    candidates['lightgbm_residual']=pred['power']
    for method,p in candidates.items():
        rows.append({'target':'power','method':method,**regression(y[:,0],p)})
        for h in HORIZONS:
            mask=info.horizon.eq(h).to_numpy();hrows.append({'target':'power','method':method,'horizon':h,'minutes':h*15,**regression(y[mask,0],p[mask])})
    for i,name in enumerate(['occupancy','arrivals','queue'],1):
        rows.append({'target':name,'method':'lightgbm_poisson',**regression(y[:,i],pred[name])})
        for h in HORIZONS:
            mask=info.horizon.eq(h).to_numpy();hrows.append({'target':name,'method':'lightgbm_poisson','horizon':h,'minutes':h*15,**regression(y[mask,i],pred[name][mask])})
    risk=classification(y[:,3]>0,pred['risk'],config['threshold'])
    risk_baseline=classification(y[:,3]>0,np.full(len(y),meta['queue_train_prevalence']),config['threshold'])
    scores=pd.DataFrame(rows);hscores=pd.DataFrame(hrows)
    scores.to_csv(OUTPUT/'metrics_test.csv',index=False);hscores.to_csv(OUTPUT/'metrics_by_horizon.csv',index=False)
    hscores[hscores.horizon.isin([1,4,12,24,48])].to_csv(OUTPUT/'metrics_selected_horizons.csv',index=False)
    write_json(OUTPUT/'classification_test.json',{'lightgbm':risk,'constant_training_prevalence':risk_baseline})
    frame=info.copy()
    for i,name in enumerate(TARGETS):frame['actual_'+name]=y[:,i];frame['pred_'+name]=pred[name]
    for name,p in candidates.items():frame[name]=p
    frame['probabilidade_fila']=pred['risk'];frame.to_csv(OUTPUT/'predictions_test.csv',index=False,float_format='%.8f')
    # Predetermined production origin; only past physically supplied to API.
    t=pd.Timestamp('2026-06-15 07:45');past=data.loc[:t].copy();forecast=engine.predict(past,t)
    poison=data.copy();poison.loc[poison.index>t,:]=np.nan
    pd.testing.assert_frame_equal(forecast,engine.predict(poison,t),check_exact=True)
    pd.testing.assert_frame_equal(forecast,engine.predict(data,t),check_exact=True)
    batch=frame[frame.timestamp_origem.eq(t)].sort_values('horizon')
    mapping={'potencia_solicitada_prevista_kw':'power','carregadores_ocupados_previstos':'occupancy','carros_chegando_previstos':'arrivals','carros_na_fila_previstos':'queue'}
    delta={}
    for c,n in mapping.items():
        delta[n]=float(np.abs(forecast[c].to_numpy()-batch['pred_'+n].to_numpy()).max())
        np.testing.assert_allclose(forecast[c],batch['pred_'+n],rtol=0,atol=1e-8)
    np.testing.assert_allclose(forecast.probabilidade_fila,batch.probabilidade_fila,rtol=0,atol=1e-8)
    assert len(forecast)==48
    forecast.to_csv(OUTPUT/'exemplo_producao_48.csv',index=False,float_format='%.8f')
    write_json(OUTPUT/'production_validation.json',{'origin':str(t),'rows':48,'future_hidden':True,'future_poison_and_delete_invariant':True,'batch_max_differences':delta})
    plots(frame,hscores,batch)
    preserved=check_preserved();write_json(OUTPUT/'preservation_validation.json',preserved)
    write_json(OUTPUT/'evaluation_completed.json',{'test':'June 2026','test_origins':int(partition_mask(data,'test').sum()),'test_long_rows':len(x),'frozen_unchanged':True,'no_model_selection_on_june':True})
    report(scores,hscores,risk,meta,len(x))
    print(scores.to_string(index=False));print(json.dumps(risk,indent=2));print(hscores[(hscores.target=='power')&(hscores.method=='lightgbm_residual')&hscores.horizon.isin([1,4,12,24,48])].to_string(index=False))
def plots(frame,scores,example):
    os.environ['MPLCONFIGDIR']=str(OUTPUT/'.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    folder=OUTPUT/'graficos';folder.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(10,4))
    for name,sub in scores[scores.target=='power'].groupby('method'):ax.plot(sub.minutes/60,sub.mae,label=name)
    ax.set(xlabel='Horizonte (h)',ylabel='MAE (kW)',title='Motor 2 | potência solicitada — junho congelado');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(folder/'erro_potencia_horizonte.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(5,1,figsize=(12,13),sharex=True)
    for ax,name,label in zip(axes,['power','occupancy','arrivals','queue'],['Potência solicitada (kW)','Ocupação máxima (carregadores)','Chegadas (veículos)','Fila máxima (veículos)']):
        ax.plot(example.timestamp_previsto,example['actual_'+name],label='Real',color='black')
        ax.plot(example.timestamp_previsto,example['pred_'+name],label='Previsto');ax.set_ylabel(label);ax.legend(fontsize=8);ax.grid(alpha=.2)
    axes[-1].plot(example.timestamp_previsto,example.probabilidade_fila,label='Probabilidade')
    axes[-1].step(example.timestamp_previsto,(example.actual_queue>0).astype(int),where='mid',label='Evento real',alpha=.7)
    axes[-1].set_ylabel('Risco de fila');axes[-1].legend();axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    fig.suptitle('48 previsões emitidas em 15/06/2026 às 08h | futuro oculto')
    fig.tight_layout();fig.savefig(folder/'previsao_completa_12h.png',dpi=150);plt.close(fig)
    sample=frame[(frame.horizon==1)&(frame.timestamp_previsto>='2026-06-15')&(frame.timestamp_previsto<'2026-06-18')]
    for name,label in [('power','Potência (kW)'),('occupancy','Ocupação'),('arrivals','Chegadas')]:
        fig,ax=plt.subplots(figsize=(12,4));ax.plot(sample.timestamp_previsto,sample['actual_'+name],label='Real');ax.plot(sample.timestamp_previsto,sample['pred_'+name],label='Previsto +15min',alpha=.8)
        ax.set(ylabel=label,title='Junho | previsões com origem móvel');ax.legend();fig.tight_layout();fig.savefig(folder/(name+'_real_previsto.png'),dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,4));ax.plot(sample.timestamp_previsto,sample.probabilidade_fila,label='Probabilidade prevista +15min')
    ax.step(sample.timestamp_previsto,(sample.actual_queue>0).astype(int),where='mid',label='Fila observada',alpha=.6);ax.legend();ax.set_ylim(-.05,1.05);fig.tight_layout();fig.savefig(folder/'risco_fila.png',dpi=150);plt.close(fig)
def report(scores,hscores,risk,meta,n):
    lines=['# Motor 2 V1 — avaliação congelada','',f"Cinco LightGBM globais, {meta['feature_count']} features, 48 horizontes em formato longo. Potência residual sobre média do slot nas quatro semanas anteriores; três regressões Poisson; um classificador binário.",'',
    f"Origens/exemplos: treino {meta['split_counts']['train_origins']}/{meta['split_counts']['train_examples']}; maio {meta['split_counts']['validation_origins']}/{meta['split_counts']['validation_examples']}; junho {n//48}/{n}. Os primeiros 28 dias fornecem contexto; as últimas 48 origens de cada partição são excluídas para nenhum alvo cruzar a fronteira.",'',
    'Maio foi usado para early stopping e threshold; junho somente após congelar. Dados sintéticos já haviam sido inspecionados na geração; independência aqui significa exclusão de junho do desenvolvimento do Motor 2, não dados reais totalmente inéditos. Pares origem/horizonte se sobrepõem.','',
    'Potência solicitada refere-se aos veículos conectados, excluindo fila e abandonos. Ocupação e fila são máximos no intervalo. Previsões de contagem são expectativas fracionárias. Sem clima ou consumo do prédio.','',
    '| Target | Método | MAE | RMSE | WAPE % |','|---|---|---:|---:|---:|']
    for r in scores.itertuples():lines.append(f'| {r.target} | {r.method} | {r.mae:.4f} | {r.rmse:.4f} | {r.wape_pct:.2f} |')
    lines+=['','## Potência por horizonte','','| Minutos | Método | MAE kW | RMSE kW | WAPE % |','|---:|---|---:|---:|---:|']
    for r in hscores[(hscores.target=='power')&hscores.horizon.isin([1,4,12,24,48])].itertuples():lines.append(f'| {r.minutes} | {r.method} | {r.mae:.4f} | {r.rmse:.4f} | {r.wape_pct:.2f} |')
    lines+=['','## Risco de fila','',f"PR-AUC trapezoidal: {risk['pr_auc']:.4f}; AP: {risk['average_precision']:.4f}; ROC-AUC: {risk['roc_auc']:.4f}; Brier: {risk['brier_score']:.4f}.",f"Threshold de maio: {risk['threshold']:.2f}; Precision: {risk['precision']:.4f}; Recall: {risk['recall']:.4f}; F1: {risk['f1']:.4f}.",'',
    'MAE de ocupação é o erro absoluto médio em número de carregadores. Brier avalia as probabilidades sem threshold. WAPE usa soma dos erros absolutos / soma dos valores reais. AP integra a curva PR por degraus; PR-AUC usa trapézios.','',
    'Produção: `src/motor_carregadores/predict.py`, função `predict(history, timestamp)` ou instância reutilizável `MotorCarregadores`. Exemplo completo: `exemplo_producao_48.csv`. A última linha t só é conhecida em t+15min; o primeiro intervalo previsto começa nesse instante de emissão. Nenhum alvo futuro entra nas features.','',
    '![Erros](graficos/erro_potencia_horizonte.png)','','![12 horas](graficos/previsao_completa_12h.png)','']
    (OUTPUT/'relatorio_motor2.md').write_text('\n'.join(lines),encoding='utf-8')
if __name__=='__main__':evaluate()
