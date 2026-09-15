# GIE Integration V1

Use esta interface. Não altere internamente os motores.

1. Crie seu ambiente Python e instale `pip install -r requirements.txt`.
2. Trabalhe a partir da raiz deste bundle, ou acrescente essa raiz ao PYTHONPATH.
3. `from gie import GIEEngine, GIEControl, History, CurrentState, EVSEState`.
4. `engine = GIEEngine()` valida Commercial_HighAutonomy_V2; `engine.initialize_models()` carrega a inferência congelada.
5. Monte `History(building=df_predio, ev=df_ev)` e `CurrentState(timestamp=t, building_kw=..., ev_demand_kw=..., solar_kw=..., battery_soc_pct=..., evses=[...])`.
6. `result = engine.run_cycle(t, history, current)`.
7. Leia `result['numeric_state']`, `result['primary_message']`, `result['messages']`, `result['visual_state']`.
8. Considere `result['execution_allowed']` e `result['health']` antes de consumir setpoints.

Cada `EVSEState(evse_id='EVSE1', connected=True, state='available', max_power_kw=22, vehicle_max_kw=11)`
tem um ID único entre EVSE1…EVSE4; fornecer sempre os quatro. connected_since é opcional.
Potências em kW, SOC em %, energia em kWh, local America/Sao_Paulo.

Históricos: timestamps locais sem fuso, contínuos a cada 15 min até t−15 min.
Prédio: mínimo 768 linhas, consumo_predio_kw, temperatura_externa_c, umidade_relativa_pct.
EV: mínimo 2689 linhas, potencia_solicitada_kw, potencia_entregue_kw, energia_entregue_kwh,
carregadores_ocupados, carros_conectados, carros_chegando, carros_na_fila, ocupacao_pct.
O timestamp t deve estar alinhado a 00/15/30/45 minutos. A decisão aplica um intervalo;
o caller fornece SOC medido e nova telemetria no ciclo seguinte. Não executar a integração
de SOC de 15 min repetidamente como se fossem passos de segundos.

NORMAL usa modelos congelados e SolarForecaster configurado para 800 kWp / 500 kW AC.
Pode consultar Open-Meteo; cache/fallback são informados em health. components pode ser
injetado com objetos compatíveis para um provider próprio. Não existe API HTTP.

## Controle de apresentação offline

`control = GIEControl(engine=engine)`
`control.set_mode('PRESENTATION')`
`control.set_presentation_interval(10)`
`control.set_loop(True)`
`control.start_presentation()`
O host chama `control.tick()` periodicamente e lê `control.get_state()`.
Também: pause_presentation, resume_presentation, stop_presentation, next_scene,
previous_scene, set_scene('08'), get_presentation_state.

`control.set_mode('MANUAL_DEMO')`; `control.trigger_demo_event('SOLAR_STRONG')`.
Outros códigos: EV_PEAK, BUILDING_PEAK, SOLAR_DROP, FAULT_EVSE1…FAULT_EVSE4,
RECOVER_EVSES, SOC_HIGH, SOC_LOW. `reset_demo()` restaura a entrada base.
Os eventos alteram somente entradas; o core real recalcula a decisão.
As 16 cenas são situações independentes com previsões explícitas, não uma série real contínua.

Uma instância por instalação/sessão; serialize chamadas concorrentes no host.
Estados visuais são representações, não comandos MPC. Setpoints são limites superiores,
não consumo medido. Quando bloqueado: comandos null e estados unknown; não são zeros válidos.
Mensagens são determinísticas e baseadas em números/eventos; nenhuma LLM é chamada.
Preservam-se também forecasts, management/plan, flows e demais informações originais.
Sem ESP32/GPIO, ACK/readback, servidor, autenticação, cobrança ou frontend.
