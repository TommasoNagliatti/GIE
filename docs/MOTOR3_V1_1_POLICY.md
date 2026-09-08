# Motor 3 V1.1 — política explícita de carga solar

Revisão autorizada para o GIE End-to-End V1. Antes de qualquer mudança foram calculados SHA-256 de 444 arquivos; fontes e testes completos do Motor 3 anterior estão em `outputs/gie_runtime/v1/motor3_before`. Os relatórios V1 e V1 rev1 permanecem intactos.

## Alteração física e execução

O MPC continua um LP contínuo de 48 passos de 15 minutos. Não foi criado MILP. O limite superior de carga por passo passou a ser:

`min(100, max(0, solar_previsto - predio_previsto - ev_esperado))`

Esses valores são parâmetros conhecidos do LP; o limite é conservador mesmo se o atendimento EV planejado ficar abaixo do esperado. O balanço continua usando 100% do solar disponível, permitindo exportação de excedentes. A bateria nunca exporta para a rede.

A projeção de execução usa os valores atuais, limites de SOC e eficiência. Seu teto de carga também é limitado a `max(0, solar_medido - predio_atual - demanda_EV_despachavel)`. Se houver excedente, o alvo de execução é carregar o máximo que couber na bateria antes de exportar. Sem excedente, a carga é zero e a projeção preserva a descarga planejada quando possível. O ajuste é escalar, sem uma árvore extensa de decisões. A carga da rede foi removida também da decomposição de fluxos e é verificada nos testes.

O Q90 continua como margem futura, não teto da demanda atual. A projeção anterior que maximiza o atendimento EV seguro permanece. Demanda que não pode ser atendida pelos EVSEs é explicitada separadamente pelo runtime.

Os parâmetros físicos são os mesmos: 200 kWh, carga/descarga 100 kW, eficiência 0,95, SOC 20–95%, reserva 30%, importação alvo 300 kW/máxima 350 kW, exportação 150 kW, EV 88 kW, solar AC 125 kW.

## Objetivo sem tarifação

Tarifas e crédito de exportação não participam mais do objetivo. Dois coeficientes abstratos explícitos substituem os termos de preços:

- Penalização por importação: 0,10.
- Penalização por exportação solar: 0,05, favorecendo armazenamento útil quando há espaço.

Os demais pesos foram preservados: excesso sobre alvo 1000, EV não atendido 100, margem Q90 10, reserva 2, reserva terminal 5, ciclagem 0,04 e desempate de fluxo 0,001. Esses coeficientes são prioridades matemáticas; não são R$/kWh, preços, custos faturáveis ou cálculo de cobrança.

`run_control(..., state=estado)` e `aligned_inputs(...)` funcionam sem tarifas. As antigas posições/nomes de argumentos foram mantidas opcionais para compatibilidade, com a antiga validação de formato; seu conteúdo é ignorado pelo objetivo. Um teste compara planos com e sem esses dados e exige igualdade completa. O runtime novo não recebe ou devolve esses campos.

## Validação

Passaram os 29 testes anteriores do Motor 3 e os testes novos do runtime, incluindo ausência de excedente real, bateria cheia/vazia, armazenamento de excedente, falha do solver, atendimento acima da previsão e balanço energético. A aceitação desta política não reutiliza nem sobrescreve resultados antigos como se fossem produzidos pela nova versão.

Arquivos alterados: config.py, constraints.py, objective.py, state.py, adapters.py, run.py, dispatch.py, validation.py e flow_allocator.py. A lista está registrada em `outputs/gie_runtime/v1/motor3_policy_revision.json`.
