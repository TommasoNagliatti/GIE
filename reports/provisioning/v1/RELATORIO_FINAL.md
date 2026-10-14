# GIE — Fase 5

Concluído localmente em 13/10/2026. Cadastro dinâmico e funcionamento BASELINE sem histórico implementados em src/gie_provisioning e integrados à extensão multiestação. Nenhum código do Backend/Site/App/banco/Docker alterado; sem commit/push/deploy ou acionamento físico.

## Resultado e demonstração

Nova estação tecnicamente validada é cadastrada, consultada, inicializada, parada e recuperada sem reiniciar as demais. Aprovação local exige token com capability de provisionamento e station_id explicitamente autorizado. Cadastro repetido é idempotente; substituição técnica é recusada. Arquivos usam paths construídos pelo servidor e checksum; processo, configuração, histórico, cache e estado individuais. Cadastro e SOC sobrevivem ao reinício do serviço.

Prova em four_stations.json: comercial original, posto, casa e NEW_NO_HISTORY, quatro PIDs distintos, via API FastAPI ASGI com workers reais. A quarta estação tem cinco carregadores de 2/3/4/5/6kW, ramal limitado, timezone America/Manaus, zero baterias/solar, nenhum CSV ou modelo emprestado. Produz 48 estimativas identificadas; sem current fica DEGRADED, com current completo/confiável executa MPC e allocator. Queda forçada e restart não alteram estado da casa e preservam o SOC/contador da nova estação. Não foi realizado deploy nem teste de rede pública.

BASELINE usa envelope técnico conservador de prédio/EV, solar futuro garantido zero e current independente para primeiro passo. Previsão não é medida. Origem permanece SIMULATED; dados ausentes, futuros, antigos ou não confiáveis não autorizam avanço. Bateria/inversor indisponíveis e rede insuficiente têm testes explícitos. A matemática Energy V3 não foi modificada.

## Testes executados

- 14 testes novos aprovados (tests_final.txt), incluindo validação técnica, autorização, concorrência/idempotência, cinco EVSEs, zero equipamentos, timezone, proveniência/freshness, falhas e quatro processos.
- 41 regressões Fase 4 aprovadas (regression_phase4.txt).
- 223 regressões comerciais aprovadas; três skips históricos mantidos pelo runner original. Logs regression_*.txt e regression_results.json.
- 2592 ciclos de 15min, 124416 passos de horizonte verificados. Dias de verão (10/02), outono (10/05), inverno (10/08) e sete dias contínuos de primavera (01–07/11/2025) por perfil novo da Fase 4. Reinício no meio de cada cenário com igualdade exata do checkpoint.
- Estação dinâmica NEW_WEEK: mais sete dias contínuos, com solar, bateria de 17kWh, cinco EVSEs, indisponibilidade de bateria no dia 3, inversor no dia 5 e restart no meio. 32256 passos, erro de balanço até 7.105e-15kW, erro de energia até 1.776e-15kWh, solver médio/máximo 247.6/443.3ms.

| Perfil / cenário | Ciclos | Prédio kWh | EV atendido kWh | Import kWh | Export kWh | Máx. erro kW | Solver médio/máx. ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| DEMO_POSTO_24H_001 / summer | 96 | 251.356 | 83.917 | 72.134 | 33.171 | 1.14e-13 | 632.6/925.6 |
| DEMO_POSTO_24H_001 / autumn | 96 | 228.046 | 149.853 | 164.151 | 0.000 | 1.31e-13 | 634.3/1205.7 |
| DEMO_POSTO_24H_001 / winter | 96 | 223.228 | 89.211 | 84.491 | 6.028 | 8.88e-14 | 576.2/975.3 |
| DEMO_POSTO_24H_001 / spring_week | 672 | 1707.863 | 824.309 | 861.967 | 121.062 | 2.70e-13 | 449.5/1269.5 |
| DEMO_CASA_001 / summer | 96 | 7.932 | 0.000 | 5.419 | 28.884 | 6.11e-16 | 192.8/286.6 |
| DEMO_CASA_001 / autumn | 96 | 7.792 | 0.000 | 5.586 | 17.971 | 1.11e-15 | 169.3/249.1 |
| DEMO_CASA_001 / winter | 96 | 7.694 | 0.000 | 5.769 | 20.929 | 1.17e-15 | 173.4/531.2 |
| DEMO_CASA_001 / spring_week | 672 | 55.679 | 18.496 | 55.225 | 180.642 | 6.84e-14 | 178.4/343.3 |

Energia é a integração kW×0,25h, sem truncamento para esconder desvios. CSVs mantêm primeira decisão de cada ciclo; summaries guardam erros máximos verificados em todos os 48 passos, SOC inicial/final, tempos e reinícios. Os ensaios sazonais são testes retrospectivos de operação, inclusive em meses usados no treino original; não são nova avaliação fora da amostra dos previsores. Recall residencial permanece 6,778%. O comercial foi validado pelas regressões/16 cenas/ciclo simultâneo; não se declara evolução multibateria contínua para sua política congelada.

## Modelos versionados e integração futura

Contratos ModelState/ModelVersion v1 preparam BASELINE, CANDIDATE, PERSONALIZED, DEGRADED, versão ativa/candidata/anterior, revisão esperada e hashes de artefato/validação para ativação/rollback por station_id. Cadastro real inicia BASELINE. Falta de current é condição operacional DEGRADED, separada do treinamento.

Ativação de novos modelos permanece deliberadamente indisponível: activation_supported=false e /model-transition retorna 409 após validar o contrato. Não há upload, treinamento automático nem promoção fictícia. Um adaptador posterior deve verificar artefatos próprios da estação, aprovação, revisão e rollback; contratos não são prova de modelo treinado.

Documentação/API, exemplos de criação/current, mapeamento do gieContract 2.0, requisitos e comandos exatos: ../../../src/gie_provisioning/README.md. O contrato do Backend não é aceito diretamente: faltas de exportação, SOC inicial, eficiências, vínculo a inversor ou circuitos precisam ser resolvidas na aprovação, sem inventar valores. IDs preservados como strings. Nenhuma alteração no EMPS.

## Preservação e limites

794 arquivos anteriores verificados, 788 idênticos; 6 alterações autorizadas somente em engines.py, manager.py, api.py e documentação da extensão multiestação. Zero diferenças inesperadas. Código Energy V3, dados, modelos, comerciais e cenas intactos. Cópias anteriores em phase4_before; detalhes em preservation_after.json. Nenhum arquivo anterior removido.

Divergência preexistente demo/high_autonomy_v2/app.py mantida sem atualização de hash. Gate global do release permanece bloqueado; suites executadas individualmente, não se declara release aprovado. Tentativa inicial de simulação dentro do sandbox falhou por permissão de diretório temporário; log preservado e execução refeita no ambiente local autorizado, sem alterar políticas do Windows.

Limites: simulação apenas; TRUSTED é uma declaração da fixture autorizada, não medidor verificado. Previsões conservadoras não garantem picos reais. Demanda EV permanece exógena, sem realimentação do SOC veicular após corte. Falta terminal de reserva adicional, homologação de inversores, telemetria física, ACK/readback, TLS, quotas/isolamento de segurança e gestão operacional de credenciais. Só um gerenciador por volume. Corrupção/conflito de cadastro bloqueia e exige inspeção, sem limpeza automática. Atualização técnica e carregamento real de novos modelos são etapas posteriores; nenhum endpoint permite alterar os equipamentos aprovados silenciosamente.

Antes da integração EMPS: adaptador técnico aprovado, credenciais por estação, disponibilidade/freshness/proveniência verificadas, cache por station_id/generation, reconciliação de respostas perdidas, política auditável de reconfiguração e modelos, backup/quotas/supervisão. Sessões, START e pagamentos continuam no Backend. physical_dispatch=false e hardware_commands_sent=false.

Inventário SHA-256 em inventory_sha256.json (exclui a si próprio, dependências, caches e runtime). Git status em git_status.txt; diff --stat vazio para arquivos rastreados porque estas extensões ainda são diretórios não versionados.
