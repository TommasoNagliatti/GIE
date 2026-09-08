def make_event(code,severity,reason,timestamp,context):
    return {'code':code,'severity':severity,'reason':reason,'timestamp':str(timestamp),'context':context}
def from_decision(row,state,c,fallback=False):
    events=[];t=row['timestamp'];tol=c.tolerance
    def add(code,reason,context,severity='info'):events.append(make_event(code,severity,reason,t,context))
    if row.get('ev_demand_above_forecast'):add('EV_DEMAND_ABOVE_FORECAST','Demanda EV observada acima da previsão pontual.',{'observed_kw':row['ev_expected_kw'],'forecast_kw':row['planned_ev_expected_kw'],'q90_kw':row['ev_high_kw']})
    if row.get('ev_block_limit_relaxed'):add('EV_BLOCK_LIMIT_RELAXED','Limite EV ampliado dentro da capacidade física disponível.',{'planned_kw':row['planned_ev_block_limit_kw'],'executed_kw':row['ev_block_limit_kw']})
    if row['battery_charge_kw']>tol and state.previous_charge_kw<=tol:add('BATTERY_CHARGE_STARTED','Carga da bateria iniciada.',{'power_kw':row['battery_charge_kw']})
    if row['battery_discharge_kw']>tol and state.previous_discharge_kw<=tol:add('BATTERY_DISCHARGE_STARTED','Descarga da bateria iniciada.',{'power_kw':row['battery_discharge_kw']})
    if row['battery_discharge_kw']>tol and row['building_kw']+row['ev_served_kw']-row['solar_utilizado_kw']>c.grid_target_kw:add('PEAK_SHAVING_ACTIVE','Bateria reduz a demanda de importação.',{'discharge_kw':row['battery_discharge_kw']})
    if row['ev_unserved_kw']>tol:add('EV_POWER_LIMITED','Parte da demanda EV esperada foi limitada.',{'unserved_kw':row['ev_unserved_kw'],'block_limit_kw':row['ev_block_limit_kw']},'warning')
    if row['grid_export_plan_kw']>tol:add('GRID_EXPORT_ACTIVE','Excedente solar exportado.',{'export_kw':row['grid_export_plan_kw']})
    if row['grid_import_plan_kw']>c.grid_target_kw+tol:add('GRID_TARGET_EXCEEDED','Importação acima do alvo operacional, dentro do limite físico.',{'import_kw':row['grid_import_plan_kw']},'warning')
    if row['battery_soc_after_pct']<c.reserve_pct-tol:add('LOW_BATTERY_RESERVE','SOC abaixo da reserva desejada, acima do mínimo absoluto.',{'soc_pct':row['battery_soc_after_pct']},'warning')
    if fallback:add('FALLBACK_ACTIVE','Programação conservadora usada após falha do solver.',{},'warning')
    return events
def explanation_payload(events,row):
    return {'language':'pt-BR','decision_time':row['timestamp'],'event_codes':[e['code'] for e in events],
        'facts':{'grid_import_kw':row['grid_import_plan_kw'],'ev_limit_kw':row['ev_block_limit_kw'],'soc_after_pct':row['battery_soc_after_pct']},
        'purpose':'Optional future explanation only; not a control instruction.','api_called':False}
