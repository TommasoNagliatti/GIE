# Relatório final — GIE Fase 3

Concluído localmente em 2026-10-12, em `C:\goodwill_ai\GIE_DATASETS`. Implementada extensão independente em `src/gie_multistation`. Nenhum arquivo anterior alterado, nenhum deploy/commit/push e nenhuma alteração em Backend, Site, App, MySQL ou Docker.

## Resultado

Um FastAPI lógico gerencia três processos internos `spawn`, cada um com GIEControl, modelos, configuração física, histórico, cache, estado de alocação, modo, mensagens e diretório de execução separados. Credenciais de serviço têm escopo explícito por station_id; não é possível trocar a identidade pelo corpo de uma requisição.

| Estação | Modelos carregados | Operação comprovada |
|---|---|---|
| Commercial_HighAutonomy_V2 | Motores 1/2 e seletores originais | Inferência, MPC/LB originais em demonstração, NORMAL/SIMULATION, Presentation e Manual Demo |
| DEMO_POSTO_24H_001 | Motores da Fase 2 e Q90 por frequência | 48 previsões/12h, demanda atual, histórico próprio; sem despacho incompatível |
| DEMO_CASA_001 | Motor 1 residencial; Motor 2/Q90 diagnóstico | 48 previsões, alerta de recall 6,78%, demanda atual independente e envelope conservador; sem despacho |

**Não há controle físico completo do posto ou da casa.** MPC e Load Balancer congelados exigem quatro EVSEs de 22kW e configuração de bateria agregada. Novos perfis declaram `dispatch_available=false`, `load_balancer_available=false`, setpoints null e visual_state inválido para comandos. Não foram inventados equipamentos para contornar validações. O próximo trabalho matemático continua sendo MPC com equipamentos variáveis e baterias individuais.

Todos os dados desta demonstração são SIMULATED. No comercial, execução matemática permitida não significa permissão física: o envelope do serviço tem physical_dispatch=false, não há transporte para hardware e hardware_commands_sent=false. SOC comercial de 50% e previsão solar constante são fixtures explicitamente identificadas, não telemetria real nem simulação contínua de bateria.

## Isolamento e recuperação

- Mailbox e lock por estação; ciclos de estações diferentes executam concorrentemente. Solicitações da mesma estação são serializadas.
- Processo morto ou timeout retorna 503 e não reutiliza resultado antigo. Encerramento afeta somente a estação alvo.
- Reinício explícito gera identificador de geração novo, NORMAL sem resultado, histórico/cache operacionais vazios e Presentation pausada. Dados antigos não são apagados: journal e snapshot por estação continuam para auditoria, sem replay de comandos.
- Trava exclusiva impede dois gerenciadores no mesmo diretório; executar Uvicorn com um worker. O isolamento é operacional por processo, não sandbox contra código hostil ou quotas de recursos por tenant.
- Registro confere hashes dos perfis, dados usados e modelos; perfis/caminhos vêm do registro confiável, nunca do corpo HTTP.
- Histórico do predictor é cortado antes do instante de emissão. Conversão temporal comercial é explícita; novos modelos conservam offset e contratos de disponibilidade da Fase 2.

## Validação executada

**17 testes novos aprovados**, com processos e modelos reais: três estações, identidade dos modelos, auth/escopo, rejeição de ID no corpo, ciclos simultâneos, isolamento de histórico/modo, validação física por estação, 16 cenas comerciais comparadas integralmente, Manual Demo, demanda residencial atual de 7kW apesar da previsão fraca, serialização, queda forçada, timeout, stop/init, reinício do worker e do gerenciador, journal separado, exclusividade e health concorrente ao lifecycle. Evidência: `tests.txt`.

**Demonstração HTTP real:** 22 requisições bem-sucedidas em loopback, três PIDs distintos, três ciclos com 48 passos, consulta de estado/health, Presentation start/pause/next/reset e parada das três estações. Evidências em `http_demo.json` e `http_demo.txt`. Servidor temporário encerrado ao final, sem serviço de produção alterado.

**Regressão original consolidada:** 223 aprovados e 3 skips históricos, usando snapshot do HEAD e ambientes apropriados. Inclui 50 testes do controle e 4 do dashboard. O runner global continua bloqueado apenas pelo mismatch preexistente de `demo/high_autonomy_v2/app.py`; nenhum hash antigo foi regravado.

A falha `test_real_step` registrada na Fase 2 foi reproduzida no snapshot sem `.venv/Scripts/python.exe`. Ao disponibilizar nele o ambiente core existente (junction local ignorada), os 6 testes de demo passaram, incluindo test_real_step. Não foi necessário alterar código. Inicialmente, o ambiente UI sem SciPy também produziu erros ao executar testes core; as suítes foram separadas nos ambientes corretos. Logs iniciais e finais permanecem disponíveis. Isso corrige a interpretação do erro de ambiente sem modificar o relatório anterior.

O ambiente Python do ecossistema antigo apresentou DLL LightGBM bloqueada pelo Windows. A execução final reutilizou o ambiente comprovado da Fase 2, com dependências FastAPI instaladas apenas em `.deps` da nova extensão. Nenhuma política de segurança ou pacote global foi modificado. Versões em `dependency_versions.json`.

## Preservação e arquivos

`preservation_before.json` e `preservation_after.json`: **685 arquivos anteriores preservados**, incluindo todos os resultados da Fase 1/Fase 2, código, modelos, seletores, MPC, Load Balancer e cenas originais. O inventário `delivery_inventory.json` lista todos os novos arquivos da Fase 3 e seus SHA-256, excluindo dependências locais, runtime e snapshot auxiliar. Não há arquivos anteriores removidos ou sobrescritos.

Novos arquivos funcionais: `registry.py`, `stations.json`, `engines.py`, `manager.py`, `api.py`, `__main__.py`, `demo.py`, `test_isolation.py`, `regression.py`, requirements e documentação dentro de `src/gie_multistation`. Relatórios somente em `reports/multistation/v1`. Git status/diff registrados em arquivos próprios; diff de arquivos rastreados vazio porque esta fase adiciona diretórios novos ainda não versionados.

## Executar e integrar depois

Comandos completos em `src/gie_multistation/README.md`; demonstração: `python -B -m gie_multistation.demo`, após configurar PYTHONPATH e o ambiente. Serviço manual: `python -B -m gie_multistation --port 8520`, com tokens de escopo explícito. Rotas e exemplos em `src/gie_multistation/API.md`; matriz matemática e relatório de isolamento em `src/gie_multistation/COMPATIBILIDADE.md`.

Limitações restantes: perfis novos sem despacho, Motor 2 residencial não aprovado para antecipação autônoma, API recebe apenas fixtures/current simulados, nenhum adaptador de telemetria física ou ingestão de histórico externo, sem TLS/proxy/quotas/deploy. No comercial, demonstrações são preservadas; nos novos perfis, Presentation/Manual Demo incompatíveis são recusados explicitamente. Não foram criadas cenas falsas para esses perfis.

Integração futura exige autorização no Backend, mapeamento aprovado de estação/equipamentos, polling/cache por station_id e generation, validação de proveniência/freshness, revisão matemática e implementação física com ACK/readback. Esta fase prepara o contrato e o isolamento; não ativa esse fluxo automaticamente.
