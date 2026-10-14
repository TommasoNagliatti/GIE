# GIE — Fase 2: relatório final

Concluído em 2026-10-12. Quatro componentes treinados e avaliados, com artefatos independentes por estação, exclusivamente sobre dados sintéticos. Nenhum modelo foi publicado ou integrado ao controle real.

## Método e seleção
Treino janeiro–agosto/2025; validação setembro–outubro; teste novembro–dezembro. Seleção e limiares congelados antes de abrir o teste, sem retreinamento ou troca do vencedor após consultá-lo. LightGBM nativo, horizonte agrupado como feature, 75 features, 48 passos de 15min. Treino com origens horárias; validação/teste com origens de 15min. Cada teste tem 5808 origens/278784 pares origem-horizonte sobrepostos, não sessões independentes.

Motor 1 compara persistência, dia anterior, semana anterior e LightGBM de 15/31 folhas. Motor 2 compara esses baselines, zero, frequência regularizada por hora/dia da semana e LightGBM com heads de potência, ocupação, chegada, fila e ocorrência. Critério inclui erro ativo/inativo e F1; candidato com recall zero é inelegível quando há positivos. Q90 escolhido separadamente por pinball na validação. Protocolo original permanece em PROTOCOL.md.

## Teste final — modelos selecionados

| Estação | Motor 1 | MAE prédio kW | RMSE prédio kW | WAPE prédio | MAE EV kW | Recall EV |
|---|---|---:|---:|---:|---:|---:|
| DEMO_POSTO_24H_001 | lightgbm_15 | 0.7407 | 0.9892 | 7.44% | 5.4220 | 73.73% |
| DEMO_CASA_001 | lightgbm_31 | 0.1657 | 0.4079 | 51.24% | 0.1549 | 6.78% |

Motor 2 selecionado: LightGBM nos dois ambientes. Q90: frequência empírica no posto; LightGBM na casa. Limiar de ocorrência 0,35 nos dois.

No Motor 1, melhor baseline de teste (semana anterior) teve MAE 0,9988 no posto e 0,1740 na casa. Selecionados: 0,7407 e 0,1657, reduções aproximadas de 25,8% e 4,8%. Na validação, MAEs selecionados foram 0,7112 e 0,1621. WAPE residencial 51,24% e picos de chuveiro subestimados continuam relevantes; baixo MAE absoluto não implica previsão perfeita.

## Limitações obrigatórias do Motor 2
- Casa: apenas 42 sessões anuais e 7 no teste. Recall 6,78%, precisão 50,55%; MAE ativo 5,7075kW, conectado 1,6312kW e inativo 0,0862kW. Todos os 2880 pares origem-horizonte de pico foram perdidos pela previsão pontual. Não são 2880 sessões. Seleção validada não autoriza uso autônomo: resultado ainda insuficiente para antecipação confiável de recargas.
- Casa: baseline semanal superou o selecionado no score do teste (0,4761 versus 0,5019); não foi promovido após abrir o teste. Zero tem MAE global 0,0767kW, mas recall zero, portanto não é considerado solução adequada. Q90 cobre 98,80% no total e apenas 2,11% dos intervalos ativos; raridade explica a cobertura global enganosa. Sem fila positiva, heads de fila/risco são constantes e métricas de detecção inaplicáveis.
- Posto: MAE ativo 7,4495kW, conectado 6,8045kW e inativo 4,1198kW. Precisão 46,84%, recall 73,73%. Score selecionado 0,1742 contra 0,1786 da frequência no teste. Suavização perde 26373 de 26404 pares de pico. Há 403 tentativas independentes no teste; consultar JSON para sessões conectadas.
- Posto: risco de fila tem recall zero com limiar 0,5 apesar de 8691 pares positivos; Brier 0,0302 não resolve essa falha. Q90 empírico tem cobertura global 90,47%, ativa 75,64% e pinball 1,7407. Não representa garantia física ou de capacidade.
- Gráficos conferidos visualmente: prédio reproduz padrões gerais; EV residencial responde tarde e perde eventos, e EV do posto suaviza picos. Nenhum resultado foi ocultado nem o teste usado para nova busca.

## Evidências entregues
Cada estação: validation_metrics.json, validation_horizons.csv, test_metrics.json, test_horizons.json, test_predictions.csv.gz, queue_calibration.json, test_session_diagnostics.csv, test_diagnostics.png e event_diagnostic.png. Diagnósticos por sessão usam potência agregada e não atribuem o consumo compartilhado a um veículo. candidate_comparison.csv compara todos os candidatos nas duas partições. Manifestos em models/stations incluem configuração, heads/constantes, schema, proveniência, hashes e referências às métricas.

## Testes e preservação
18 testes novos passaram, incluindo causalidade, timezone, limites, integridade, insuficiência de histórico, isolamento por estação e retreinamento determinístico exato do building_15 nas duas estações.
Regressões originais em snapshot isolado do HEAD: 161 aprovados e 3 skips nas suítes de core/runtime/MPC/LoadBalancer/integrações/observabilidade/high_autonomy/simulação. Ambiente de demo correto: mais 7 aprovados e 1 erro (test_real_step: sim_state None). Total de regressões individuais: 168 aprovados, 3 skips, 1 erro. Tentativas iniciais no ambiente core falharam por falta de Streamlit e foram repetidas no ambiente da demo; logs preservados. A falha de UI ocorreu também no snapshot original sem este pipeline; não foi corrigida fora do escopo.
Runner global bloqueado pela divergência preexistente em demo/high_autonomy_v2/app.py. Hash não atualizado. Comparação SHA-256 dos 592 arquivos anteriores em preservation_after.json comprova preservação, incluindo dados da Fase 1. Sem mudanças em Backend/Site/App, MPC, LoadBalancer, GIEControl, cenas ou modelos originais; sem commit/push/deploy.

## Reprodução e próxima etapa
Comandos completos, dependências fixadas e exemplo de inferência em src/station_forecasts/README.md (caminho a partir da raiz). Não sobrescrever entrega: novos treinos/avaliações em cópia separada. Modelos disponíveis para integração técnica futura por station_id, mas Motor 2 necessita melhora e validação em nova partição independente antes de decisões autônomas, principalmente na residência. Dados reais e mais sessões são necessários para validar generalização. Serviço multiestação e MPC multibateria não implementados nesta fase.

Inventário e hashes: delivery_inventory.json. Estado Git final: git_status.txt e git_diff_stat.txt. Arquivos desta fase somente em src/station_forecasts, models/stations e reports/station_forecasts; demais diretórios não rastreados já pertenciam à Fase 1.
