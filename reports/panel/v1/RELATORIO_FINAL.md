# GIE — Fase 5.5

Entrega local finalizada em 14/10/2026, com testes realizados em 13/10. Painel Streamlit em **http://127.0.0.1:8504**, API autenticada em 8520 e acesso ao painel original em 8503. Inicialização por `run_multistation_panel.bat`, na raiz. Instruções completas em `src/gie_panel/README.md`.

## Implementado

- Quatro estações independentes: comercial original, posto 24h, residência e NEW_NO_HISTORY.
- Fluxos, potências em kW, energia em kWh, origem/estado/instante, equipamentos reais do cadastro e gráficos de previsão/histórico. Posto com duas baterias; casa sem SOC fictício; banco comercial explicitamente agregado.
- Replay somente leitura separado de runtime interativo com novos IDs de teste/checkpoints. Cenários sazonais, 96 ciclos, velocidade visual, pausa, reset isolado, reinício de worker e recuperação do contador pelo checkpoint.
- Presentation original com 16 cenas, autoplay, anterior/próxima, loop e intervalos; Manual Demo usa os eventos originais. UI chama HTTP; matemática executa exclusivamente nos workers da API.
- Central SQLite local persistente, filtros, reconhecimento, resolução observada, histórico por cursor, IDs/revisões, deduplicação, histerese e recuperação após reinício. Nenhum transporte de notificação comercial.
- Flags de simulação preservadas. Nulos não viram zero, setpoints não são chamados de consumo medido e perda de comunicação remove o resultado atual.

## Auditoria e decisões

As mensagens determinísticas de `gie_control/messages.py`, o histórico do controle, DecisionLog/trace e os eventos multiestação já existiam. Nenhum deles oferecia reconhecimento/resolução persistentes por estação. A central acrescenta esse ciclo de vida e reutiliza os reason_codes/mensagens existentes; não substitui a matemática nem inventa diagnósticos internos do solver.

O gateway EMPS já tem outbox local de desenvolvimento para station-review/station-invite. A extensão não cria outro transporte nem toca no Backend. O contrato 1.0 e a futura responsabilidade de autorização/destinatários/idempotência do Backend estão em `src/gie_panel/EVENTS.md`, com exemplos em `event_examples.json`.

## Validação

- **10 testes do painel/API** distintos aprovados, incluindo 192 ciclos reais: 96 do posto e 96 da residência, cada um com horizonte de 48 passos. Logs `tests_final.txt`, `lifecycle_final.txt` e `restart_concurrency_final.txt`; prova numérica `interactive_96.json`. Incluem execução simultânea e persistência de índices separados por estação.
- **1 teste de interface** aprovado com quatro payloads reais de replay, troca de estação, equipamentos, formatação e remoção dos valores ao desconectar (`ui_tests_final.txt`).
- **55 regressões das Fases 3–5** aprovadas (`regression_phase345_final.txt`).
- **223 regressões originais** aprovadas, com três skips históricos mantidos (`regression_results.json`, `regression_*.txt`). Incluem 50 testes do controle e quatro do dashboard original.
- Testes de falha/recuperação de EVSE, SOC mínimo, telemetria ausente, MPC inviável, demanda não atendida, disponibilidade explícita de equipamentos, deduplicação, ACK sem resolução, persistência após reinício completo da API e isolamento de estação.
- Navegador real: quatro estações, previsões/duas baterias do posto, casa sem bateria, BASELINE com cinco EVSEs, ciclo via botão, reconhecimento preservando a falha, telemetria ausente mostrando “—”, e desconexão real da API sem dados antigos. Capturas PNG nesta pasta.

Falhas intermediárias corrigidas: seleção incorreta de widget no teste de UI; transporte em cache durante recarga de código; duplicação de observação de cena entre comando e polling; estado parado consultado como erro; regressão com nome de módulo incorreto. Regressões finais registram os resultados válidos. A execução em sandbox falhou por permissão de temporários; testes foram concluídos no ambiente local autorizado.

## Preservação — ressalva explícita

Comparados **875 arquivos** com a referência anterior. **873 permaneceram byte a byte iguais**. Alterações identificadas:

1. `src/gie_multistation/api.py`: extensão opcional `panel_dir`, lifecycle e rotas do painel; uso padrão anterior preservado.
2. **Exceção involuntária:** `reports/provisioning/v1/four_stations.json` foi regravado por uma escrita fixa no teste preexistente da Fase 5 durante a regressão. Não havia cópia integral anterior recuperável nesta entrega; o hash anterior foi preservado em `preservation_before.json`. Não se declara preservação byte a byte desse JSON. O arquivo regenerado registra workers de teste e está identificado no inventário. Não foi alterado o hash antigo para ocultar a diferença.

Criado `gie_panel.regression` para redirecionar essa escrita para `reports/panel/v1/regression_outputs`, evitando novas alterações em evidências anteriores. Datasets, modelos, políticas MPC, cenas, checkpoints anteriores, Site/App/Backend/MySQL e Docker não foram alterados. O mismatch preexistente de `demo/high_autonomy_v2/app.py` foi mantido; nenhum hash congelado foi atualizado. Sem commit, push ou deploy.

## Limitações e próxima etapa

- Somente simulação local. Não há telemetria física, envio de comandos ou notificações reais.
- Modelo EV residencial mantém baixa confiabilidade. BASELINE não é modelo personalizado.
- Replay salvo BASELINE possui um ciclo; replays sazonais fora da primavera não guardam previsões. Campos ausentes permanecem desconhecidos. O interativo calcula novos horizontes pelo runtime existente.
- Banco comercial é agregado pelo contrato original. Não são fabricadas baterias individuais, entrega individual de EVSE ou disponibilidade física onde não há observação.
- A autenticação do painel local é de serviço; auditoria de usuário humano e destinatários pertencem à futura integração EMPS.
- O ledger mantém eventos anteriores, sem limpeza automática. Consulta oferece páginas de 500; UI mostra a primeira página e a API permite continuar por cursor.

## Arquivos e operação

Novos: `src/gie_panel/` (interface, transporte HTTP, serviço de testes, alertas, adaptadores de replay, launcher, testes e documentação), `run_multistation_panel.bat`, `reports/panel/v1/` (relatório/evidências/inventário). Nenhum arquivo removido. Alterados os dois arquivos explicitados acima.

O launcher usa os ambientes Python existentes, não instala pacotes e não encerra portas de terceiros. Se a porta 8503 já está ocupada, preserva o painel original. Na validação os serviços novos foram reiniciados de forma controlada e permanecem locais. O inventário exclui runtime, SQLite, logs temporários e credenciais.

`git_status.txt` e `git_diff_stat.txt` registram o estado final. Muitos diretórios das fases anteriores já eram não rastreados; por isso `git diff --stat` não enumera seu conteúdo. A lista completa desta entrega está em `inventory.json`.
