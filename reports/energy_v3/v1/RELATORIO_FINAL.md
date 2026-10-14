# Fase 4 — Energy V3 concluída em simulação

Implementação independente em `src/gie_energy_v3`: MPC MILP de 48×15min, Load Balancer variável, SOC individual persistente e guarda física dos 48 passos. Posto e residência executam o novo motor; comercial mantém MPC/allocator originais, modos e 16 cenas. Nenhum transporte físico, commit, push ou deploy foi ativado. Backend/Site/App/MySQL/Docker não foram alterados.

## Resultados de 24 horas

96 ciclos por estação em 01/11/2025, total de 9.216 passos de horizonte verificados. Reinício após ciclo 48 preservou exatamente o checkpoint em ambas. Somente o primeiro passo de cada plano foi aplicado ao estado SIMULATED. Demanda e geração são fixtures sintéticas; não representam operação real.

| Perfil | Edificação kWh | EV solicitado / atendido kWh | Solar usado kWh | Import / export kWh | SOC final |
|---|---:|---:|---:|---:|---|
| DEMO_POSTO_24H_001 | 247.523 | 133.211 / 133.211 | 284.186 | 92.830 / 15.384 | BAT_01: 20.00%, BAT_02: 30.67% |
| DEMO_CASA_001 | 8.309 | 18.496 / 18.496 | 31.278 | 23.687 / 28.161 | sem bateria |

Posto: as duas baterias evoluem separadamente, chegam ao máximo e voltam a fornecer energia à noite. Casa: sem bateria, exporta excedente diurno e importa para a recarga noturna, respeitando carga doméstica prioritária. As diferenças são consequências de equipamentos/demandas diferentes, não comparação de eficiência entre algoritmos. Energia = soma(kW×0,25h); os campos de `totals_kwh` conservam nomes das séries kW, mas seus valores são integrais em kWh.

Erro máximo de balanço: posto 8,58e-14 kW; casa 6,84e-14 kW. Erro de evolução individual: até 1,78e-14 kWh. Tempo médio/máximo por otimização: posto 154/294ms; casa 50/104ms, neste computador e cenário. Gráficos conferidos visualmente, CSVs e planos em cada subpasta station_id. Não usar os tempos como SLA.

## Validação

- 41 testes finais: 23 matemáticos, 1 teste integrado com múltiplas verificações de continuidade/falha, 17 testes multiestação. Log `final_tests.txt`.
- 223 regressões originais aprovadas; 3 verificações históricas de arquivos privados puladas pelo runner original. Controle 50 e dashboard 4 incluídos. Logs `regression_*.txt` e índice JSON.
- Zero/uma/duas baterias; SOC distinto, mínimos/máximos, indisponibilidade e inversor compartilhado; ausência de solar; curtailment/export; carga obrigatória inviável; circuitos; mínimos EVSE; justiça/veículo/desconexão; ausência de ciclos artificiais; NaN; demanda atual residencial; replay/gaps; crash e restauração de energia; checkpoint inválido bloqueado; isolamento e nenhum comando físico.
- A primeira execução sequencial revelou inviabilidade numérica no último desempate, com ótimos anteriores válidos. Tolerância dos objetivos aumentada de 1e-7 para 1e-5 kWh (0,01Wh); tolerância da guarda física permaneceu 2e-5. Falha original preservada em `simulation_attempt_01.txt`. Duas expectativas de igualdade de ótimo nos testes passaram a usar 4,1e-5 kW, correspondente a esse orçamento de objetivo em 15min; nenhuma restrição física foi relaxada. Pequeníssimos déficits/cortes numéricos estão registrados, não truncados nos CSVs.

## Preservação e alterações

730 arquivos anteriores conferidos; 722 idênticos e 8 alterações autorizadas na extensão multiestação. Nenhuma alteração inesperada. CommercialEngine permanece textual e integralmente igual. Modelos, datasets, cenas e núcleo comercial preservados.

Alterações da Fase 3: factory dos novos workers em engines.py; checkpoint/tempo/capacidades no manager.py; campos opcionais de demanda em api.py; expectativa de despacho matemático em test_isolation.py; capacidades declaradas em stations.json; documentação atualizada. Cópias anteriores estão em `phase3_before`. Código novo completo em `src/gie_energy_v3`; arquivos anteriores não foram removidos.

Mismatch legado conhecido: `demo/high_autonomy_v2/app.py` já divergia do manifesto original antes desta fase. Não foi editado nem teve hash atualizado. Por isso o gate global do release continua bloqueado por esse mismatch; as suites foram executadas separadamente. Não se declara release global aprovado.

## Segurança e limites

Toda execução é SIMULATED. execution_allowed indica validade matemática, jamais autorização física. Checkpoints preservam somente energia simulada; não restauram comandos. Falhas inviáveis não avançam SOC. Modelo residencial continua com recall 6,778%; demanda atual prevalece e o envelope futuro é conservador, não previsão calibrada.

Política solar_only_lex_v3.0 sem tarifa inventada. Baterias têm estados individuais, com direção comum conservadora e sem exportação de energia armazenada. Envelope de inversor PV+C+D é conservador; não homologa equipamento real. Disponibilidades de baterias/inversores são configuradas; não há ingestão de telemetria física. A demanda EV é exógena e não realimenta SOC de veículos após cortes. Sem reserva terminal adicional, envelhecimento, fases ou controle físico. Um dia validado não prova viabilidade anual. Falhas de volume/disco e integração distribuída exigem etapa operacional própria.

Formulação: `FORMULACAO.md`. Contratos, limitações completas e comandos exatos: `../../../src/gie_energy_v3/README.md`. Evidência de preservação: `preservation_after.json`. Inventário SHA-256: `inventory_sha256.json`, exclui a si próprio, caches, dependências e snapshots auxiliares.

Próxima etapa: ampliar cenários sazonais e políticas de disponibilidade/veículos antes de qualquer integração com telemetria real. Qualquer acionamento físico exige interfaces verificadas, limites homologados, ACK/readback, supervisão e autorização específica.
