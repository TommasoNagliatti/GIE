# Motor 3 V1 — revisão 1: execução com demanda observada

A revisão altera apenas dispatch.py, events.py e run.py. Fontes anteriores em source_before; resultados anteriores em ../v1. Motor 1, Motor 2, formulação MPC, pesos e parâmetros físicos foram preservados e conferidos por SHA-256.

## Regra de execução

A demanda EV atendida é min(demanda observada, 88, max(0, 350 + solar + descarga disponível pelo SOC − prédio)). Se nem o prédio puder ser atendido, a execução é bloqueada por PhysicalInfeasibleError. A descarga disponível respeita potência, eficiência e energia até SOC mínimo.

Depois de maximizar o atendimento EV, projeta-se a potência líquida planejada da bateria no intervalo físico viável mais próximo. A projeção respeita importação/exportação, carga/descarga, SOC, ausência de simultaneidade e ausência de exportação da bateria. O bloco EV é ampliado até o atendimento necessário, limitado pela capacidade efetivamente disponível. Q90 continua sendo margem de planejamento.

O alvo de 300 kW continua no MPC. Na execução, pode ser ultrapassado para atender EV, respeitando o teto físico de 350 kW. Não foram alterados pesos para obter esse comportamento.

## Interface de produção

run_control(..., execution_measurements=Measurements(timestamp_do_passo_zero, building_kw, ev_kw, solar_kw)) aceita medições atuais. O timestamp deve corresponder ao primeiro passo; leituras defasadas são rejeitadas. O argumento measurements anterior continua representando o último intervalo concluído. Sem execution_measurements, mantém-se a interface de planejamento anterior.

Com medições atuais, first_decision e os comandos de nível superior representam a execução corrigida; planned_first_decision e plan preservam o planejamento. Somente o primeiro passo é executado; o SOC medido/realizado deve alimentar o ciclo seguinte. Exceções de inviabilidade impedem retorno de comandos executáveis.

EV_DEMAND_ABOVE_FORECAST compara a demanda observada com a previsão pontual e inclui Q90 no contexto. EV_BLOCK_LIMIT_RELAXED informa a ampliação. Ambos são eventos info, sem indicação de falha. execution_adjusted registra qualquer ajuste; safety_override identifica redução física do limite planejado.

## Revalidação

29 testes passaram: 20 originais e 9 novos, incluindo 500 casos físicos reproduzíveis no teste de conservação/maximalidade.

| Cenário | EV não atendido antes (kWh) | Depois (kWh) | Importação máxima (kW) | Energia acima do alvo de 300 kW (kWh) |
|---|---:|---:|---:|---:|
| Integração 48h | 11.835241 | 0.000000 | 273.720037 | 0.000000 |
| Estresse 72h | 579.393148 | 0.000000 | 350.000000 | 579.393148 |

Foram repetidos os mesmos períodos, perfis, SOC inicial, tarifas e solar fictícios da V1. A integração usa os Motores 1/2 congelados, realimentação em memória e dados realizados somente no instante de execução. Os valores de 15 minutos são aproximações da telemetria atual na simulação; não representam teste em equipamento físico. Sessões e fila continuam exógenas.

O máximo seguro é instantâneo, considerando a energia disponível no SOC do ciclo. Esta correção não promete eliminar toda demanda não atendida em cenários de capacidade insuficiente, nem otimiza com conhecimento futuro real.

integrated: SOC 20.393669–95.000000%; erro máximo de balanço 5.68e-14 kW; erro SOC/energia 1.42e-14 kWh; eventos {'EV_DEMAND_ABOVE_FORECAST': 44, 'BATTERY_DISCHARGE_STARTED': 10, 'BATTERY_CHARGE_STARTED': 7, 'EV_BLOCK_LIMIT_RELAXED': 7, 'LOW_BATTERY_RESERVE': 2}.
mock_stress: SOC 20.000000–95.000000%; erro máximo de balanço 0 kW; erro SOC/energia 4.17e-14 kWh; eventos {'GRID_EXPORT_ACTIVE': 102, 'EV_BLOCK_LIMIT_RELAXED': 48, 'PEAK_SHAVING_ACTIVE': 48, 'GRID_TARGET_EXCEEDED': 48, 'BATTERY_CHARGE_STARTED': 18, 'LOW_BATTERY_RESERVE': 6, 'BATTERY_DISCHARGE_STARTED': 5}.