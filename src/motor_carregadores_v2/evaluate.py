"""Diagnóstico junho congelado; nenhuma seleção ou calibração."""
import sys,os
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_carregadores_v2.features import *
from motor_carregadores_v2.predict import MotorCarregadores
from motor_carregadores.metrics import regression
def quantile_metrics(y,q,point):
    upper=np.maximum(q,point);error=y-q
    return {'raw_q90_coverage_pct':float(np.mean(y<=q)*100),'upper_coverage_pct':float(np.mean(y<=upper)*100),
        'raw_pinball_loss':float(np.maximum(.9*error,-.1*error).mean()),
        'upper_pinball_loss':float(np.maximum(.9*(y-upper),-.1*(y-upper)).mean()),
        'q90_below_point_pct':float(np.mean(q<point)*100),'mean_upper_kw':float(upper.mean()),
        'mean_margin_kw':float((upper-point).mean()),'n':len(y)}
def evaluate():
    if (OUTPUT/'evaluation_complete.json').exists():raise RuntimeError('Diagnóstico já concluído.')
    verify('freeze_manifest.json');verify('preservation_before.json')
    engine=MotorCarregadores();data=load_data();x,y,b,info=make_long(data,'test')
    residual=np.clip(b[:,3]+engine.v1.models['power'].predict(x,num_threads=2),0,88)
    c={'persistencia':b[:,0],'semana_anterior':b[:,2],'media_4semanas':b[:,3],'residual_v1':residual}
    hybrid=np.empty(len(x))
    for row in engine.selection:
        mask=info.horizon.eq(row['horizon']).to_numpy();hybrid[mask]=c[row['method']][mask]
    q=np.clip(engine.quantile.predict(x,num_threads=2),0,88);upper=np.maximum(q,hybrid)
    candidates={'media_4semanas':b[:,3],'residual_v1':residual,'hibrido_v2':hybrid}
    overall=[];scores=[];coverage=[]
    for name,p in candidates.items():
        overall.append({'method':name,**regression(y[:,0],p)})
        for h in HORIZONS:
            m=info.horizon.eq(h).to_numpy();scores.append({'method':name,'horizon':h,'minutes':h*15,**regression(y[m,0],p[m])})
    for h in HORIZONS:
        m=info.horizon.eq(h).to_numpy();coverage.append({'horizon':h,'minutes':h*15,**quantile_metrics(y[m,0],q[m],hybrid[m])})
    totals=pd.DataFrame(overall);byh=pd.DataFrame(scores);cov=pd.DataFrame(coverage)
    totals.to_csv(OUTPUT/'metrics_overall.csv',index=False);byh.to_csv(OUTPUT/'metrics_by_horizon.csv',index=False)
    byh[byh.horizon.isin([1,4,12,24,48])].to_csv(OUTPUT/'metrics_selected_horizons.csv',index=False)
    cov.to_csv(OUTPUT/'quantile_by_horizon.csv',index=False)
    qm=quantile_metrics(y[:,0],q,hybrid);write_json(OUTPUT/'quantile_overall.json',qm)
    frame=info.copy();frame['real_kw']=y[:,0]
    for name,p in candidates.items():frame[name]=p
    frame['q90_raw_clipped_kw']=q;frame['potencia_solicitada_alta_kw']=upper
    frame.to_csv(OUTPUT/'predictions_diagnostic_june.csv',index=False,float_format='%.8f')
    t=pd.Timestamp('2026-06-15 07:45');past=data.loc[:t].copy();forecast=engine.predict(past,t)
    poison=data.copy();poison.loc[poison.index>t,:]=np.nan
    pd.testing.assert_frame_equal(forecast,engine.predict(poison,t),check_exact=True)
    v1=engine.v1.predict(past,t)
    cols=['carregadores_ocupados_previstos','carros_chegando_previstos','carros_na_fila_previstos','probabilidade_fila']
    pd.testing.assert_frame_equal(forecast[cols],v1[cols],check_exact=True)
    batch=frame[frame.timestamp_origem==t].sort_values('horizon')
    np.testing.assert_allclose(forecast.potencia_solicitada_prevista_kw,batch.hibrido_v2,atol=1e-8,rtol=0)
    np.testing.assert_allclose(forecast.potencia_solicitada_alta_kw,batch.potencia_solicitada_alta_kw,atol=1e-8,rtol=0)
    assert len(forecast)==48 and np.allclose(forecast.energia_solicitada_prevista_kwh,forecast.potencia_solicitada_prevista_kw*.25)
    assert np.isfinite(hybrid).all() and np.isfinite(upper).all() and ((hybrid>=0)&(hybrid<=upper)&(upper<=88)).all()
    forecast.to_csv(OUTPUT/'exemplo_producao_48.csv',index=False,float_format='%.8f')
    ranges=[]
    for r in engine.selection:
        if ranges and ranges[-1]['method']==r['method']:ranges[-1]['end_minutes']=r['minutes']
        else:ranges.append({'method':r['method'],'start_minutes':r['minutes'],'end_minutes':r['minutes']})
    counts=pd.Series([r['method'] for r in engine.selection]).value_counts().to_dict()
    write_json(OUTPUT/'selection_summary.json',{'counts':counts,'ranges':ranges})
    plots(byh,cov,batch)
    preserved=verify('preservation_before.json');verify('freeze_manifest.json')
    write_json(OUTPUT/'evaluation_complete.json',{'june_role':'secondary diagnostic','n':len(x),'origins':len(x)//48,
        'preserved_files':preserved,'unchanged':True,'production_rows':48,'other_outputs_identical_to_v1':True,
        'future_poison_and_delete_invariance':True,'batch_matches_production':True,'no_post_june_changes':True})
    lines=['# Motor 2 V2 — híbrido e potência alta','',
        'V1 e Motor 1 preservados. Nenhum retreino de ocupação, chegadas, fila ou risco; os mesmos modelos V1 são carregados. Um novo LightGBM global Q90 usa as 217 features V1, treino janeiro–abril e early stopping em maio. O seletor minimiza MAE por horizonte apenas em maio. Junho é diagnóstico secundário: a V1 já havia sido avaliada nele e motivou esta evolução.','',
        'A saída alta é max(previsão pontual, Q90 limitado a 0–88). A regra foi definida antes do teste e garante ordenação; não calibra cobertura para 90%. Cobertura bruta e operacional são reportadas separadamente. É um limite marginal por intervalo, não garantia de 90% para toda a trajetória de 12h. Potência solicitada continua excluindo os veículos na fila.','',
        '| Método | MAE kW | RMSE kW | WAPE % |','|---|---:|---:|---:|']
    for r in totals.itertuples():lines.append(f'| {r.method} | {r.mae:.4f} | {r.rmse:.4f} | {r.wape_pct:.2f} |')
    lines+=['','## Horizontes','','| Minutos | Método | MAE kW | RMSE kW | WAPE % |','|---:|---|---:|---:|---:|']
    for r in byh[byh.horizon.isin([1,4,12,24,48])].itertuples():lines.append(f'| {r.minutes} | {r.method} | {r.mae:.4f} | {r.rmse:.4f} | {r.wape_pct:.2f} |')
    lines+=['','## Cobertura','',f"Q90 bruto limitado: {qm['raw_q90_coverage_pct']:.2f}%; potência alta operacional: {qm['upper_coverage_pct']:.2f}%. Cruzamentos Q90 < pontual: {qm['q90_below_point_pct']:.2f}%. Pinball Q90 bruto: {qm['raw_pinball_loss']:.4f} kW.",'',
        '## Seleção de maio','',str(counts),'',str(ranges),'',
        'Produção: `src/motor_carregadores_v2/predict.py`; 48 linhas, 8 colunas. Histórico mínimo: 2.689 linhas. Timestamp t é início da última medição, disponível em t+15min. Dados futuros ocultos ou substituídos por nulos não mudaram a previsão.','',
        '![Erros](graficos/erro_horizonte.png)','','![Cobertura](graficos/cobertura_horizonte.png)','','![12h](graficos/exemplo_12h.png)','']
    (OUTPUT/'relatorio_v2.md').write_text('\n'.join(lines),encoding='utf-8')
    print(totals.to_string(index=False));print(json.dumps(qm,indent=2));print(json.dumps({'counts':counts,'ranges':ranges},indent=2))
def plots(scores,cov,sample):
    os.environ['MPLCONFIGDIR']=str(OUTPUT/'.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    folder=OUTPUT/'graficos';folder.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(10,4))
    for name,sub in scores.groupby('method'):ax.plot(sub.minutes/60,sub.mae,label=name)
    ax.set(xlabel='Horizonte (h)',ylabel='MAE (kW)',title='Junho | diagnóstico com V2 congelada');ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(folder/'erro_horizonte.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4));ax.plot(cov.minutes/60,cov.raw_q90_coverage_pct,label='Q90 bruto');ax.plot(cov.minutes/60,cov.upper_coverage_pct,label='Alta operacional',ls='--');ax.axhline(90,color='gray',ls=':');ax.set(xlabel='Horizonte (h)',ylabel='Cobertura (%)');ax.legend();fig.tight_layout();fig.savefig(folder/'cobertura_horizonte.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,4));ax.plot(sample.timestamp_previsto,sample.real_kw,label='Real',color='black');ax.plot(sample.timestamp_previsto,sample.hibrido_v2,label='Híbrido V2');ax.plot(sample.timestamp_previsto,sample.potencia_solicitada_alta_kw,label='Alta Q90',ls='--');ax.fill_between(sample.timestamp_previsto,sample.hibrido_v2,sample.potencia_solicitada_alta_kw,alpha=.15);ax.set(ylabel='kW',title='15/06/2026 às 08h | previsão completa de 12h');ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'));ax.legend();fig.tight_layout();fig.savefig(folder/'exemplo_12h.png',dpi=150);plt.close(fig)
if __name__=='__main__':evaluate()
