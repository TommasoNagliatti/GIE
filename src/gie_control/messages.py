"""Evidence-only Portuguese messages, independent of any LLM or network."""
EPS = 1e-5

def fmt(value): return f'{value:.1f}'.replace('.', ',')

def messages_for(result):
    n=result['numeric_state']; messages=[]
    def add(title,text,action,codes,context,severity='info'):
        messages.append(dict(title=title,text=text,severity=severity,action=action,
                             reason_codes=codes,numeric_context=context))
    if not result['execution_allowed']:
        add('Execução bloqueada','Não há novos setpoints autorizados. Consulte health e events.',
            'execution_blocked',['EXECUTION_BLOCKED'],{'status':result['status']},'critical')
        return messages
    for event in result.get('events',[]):
        if event.get('severity') in ('critical','error'):
            add('Evento crítico: '+event['code'],'Consulte o registro original do componente.',
                'event',[event['code']],event.get('context',{}),event['severity'])
    for id,device in n['evses'].items():
        if device.get('state') in ('fault','offline'):
            i=int(id[-1]);value=n['evse_setpoints_kw'][i-1]
            add(f'EVSE {i} indisponível',f'Limite alocado: {fmt(value)} kW. Os demais limites estão no painel.',
                'evse_unavailable',['EVSE_FAULT' if device['state']=='fault' else 'EVSE_OFFLINE'],
                {'evse_id':id,'state':device['state'],'allocated_kw':value},'warning')
    specs=[('grid_export_kw','Exportação para a rede','O excedente está sendo exportado.','GRID_EXPORT_SURPLUS'),
           ('battery_charge_kw','Excedente solar — bateria carregando','A bateria recebe excedente solar disponível.','SOLAR_SURPLUS'),
           ('battery_discharge_kw','Bateria em descarga','A bateria fornece potência às cargas atuais.','BATTERY_SUPPLY_TO_LOAD'),
           ('grid_import_kw','Importação da rede','A rede fornece parte da potência consumida.','GRID_DEFICIT_SUPPLY')]
    for key,title,text,code in specs:
        if n[key]>EPS:
            add(f'{title} — {fmt(n[key])} kW',text,key,[code],{key:n[key]})
    if n['ev_unserved_kw']>EPS:
        add(f'Demanda EV não atendida — {fmt(n["ev_unserved_kw"])} kW',
            'A entrega EV é inferior à demanda observada; consulte os limites e estados dos EVSEs.',
            'ev_limited',['EV_POWER_LIMITED'],{'ev_unserved_kw':n['ev_unserved_kw']},'warning')
    forecast=((result.get('forecasts') or {}).get('records') or [{}])[0]
    if n['ev_demand_kw']>forecast.get('potencia_solicitada_prevista_kw',float('inf'))+EPS:
        add('Demanda EV acima da previsão','A medição atual supera a previsão do intervalo.',
            'ev_above_forecast',['EV_DEMAND_ABOVE_FORECAST'],{'ev_demand_kw':n['ev_demand_kw'],
            'forecast_ev_kw':forecast['potencia_solicitada_prevista_kw']})
    if not messages:
        add('Equilíbrio energético atual','Sem carga/descarga de bateria nem intercâmbio relevante com a rede.',
            'balanced',['ENERGY_BALANCED'],{'energy_balance_error_kw':n['energy_balance_error_kw']})
    return messages
