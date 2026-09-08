# GIE End-to-End V1

O repositório permanece exclusivamente GIE — Gerenciamento Inteligente de Energia. Este módulo conecta os Motores 1/2 congelados, integração solar, Motor 3 V1.1 e Load Balancer. Não contém frontend, gestão de usuários, cobrança, pagamentos, serviços da GoodWe ou chamadas a LLM. Os exemplos históricos do repositório permanecem preservados; seus antigos parâmetros de tarifa não fazem parte do fluxo novo.

## Função pública

```python
from gie_runtime import Components, History, CurrentState, run_gie_cycle

# Carregar uma vez e reutilizar os componentes entre ciclos.
componentes = Components.real()
historico = History(historico_predio, historico_ev)
atual = CurrentState(
    timestamp=decision_time,
    building_kw=predio_atual_kw,
    ev_demand_kw=demanda_ev_atual_kw,
    solar_kw=solar_medido_kw,
    battery_soc_pct=soc_medido,
    evses=quatro_estados_evse,
)
saida = run_gie_cycle(decision_time, historico, atual, componentes)
```

Executar com `src` no PYTHONPATH, por exemplo `$env:PYTHONPATH="src"` no PowerShell. Há argumentos opcionais config (Config do Motor 3), balancer_config e balancer_state. Para o próximo ciclo, use o SOC e medições realmente disponíveis; não execute os outros 47 passos do plano. O `next_state` retornado pelo Load Balancer pode ser reconstruído como BalancerState para manter eventos de conexão e desempates.

## Contrato temporal e de dados

Um ciclo representa 15 minutos, com início exatamente em um quarto de hora. O timestamp atual deve ser o mesmo do ciclo. Datas com fuso são convertidas para São Paulo; o contrato local dos motores congelados usa timestamps sem fuso. Históricos devem ser contínuos e terminar em `decision_time − 15 minutos`. Dados posteriores são retirados antes da inferência. O Motor 1 requer pelo menos 768 linhas; o Motor 2, 2689.

O Motor 1 e o Motor 2 recebem o último intervalo concluído e produzem a partir de decision_time. A integração solar também recebe decision_time. Os três índices de 48 passos são comparados integralmente, não apenas por tamanho. A conversão de fim/início de intervalo da Open-Meteo permanece na integração solar original.

Histórico, estado atual e configuração física são objetos separados. O plano usa as previsões futuras; a primeira ação usa explicitamente consumo atual, demanda EV disponível, solar medido e SOC. O cache/fallback meteorológico não substitui o solar atual medido.

## Fluxo e falhas

1. Validação do ciclo e telemetria.
2. Inferência real do Motor 1 e do Motor 2.
3. Solar por Open-Meteo, cache válido ou fallback zero.
4. Validação conjunta dos 48 timestamps.
5. Checagem da capacidade EVSE pelo Load Balancer existente.
6. MPC e projeção da primeira ação pelo Motor 3 existente.
7. Distribuição do bloco EV pelo Load Balancer existente.
8. Verificação de balanço e emissão de uma única estrutura serializável em JSON.

O runtime não reimplementa modelos, MPC ou max-min fairness. A checagem prévia dos EVSEs usa o próprio Load Balancer. Se mínimos de hardware reduzirem a capacidade abaixo da entrega calculada, somente a ação corrente ainda não aplicada é reprojetada pelo próprio Motor 3 e redistribuída; não há novo treinamento ou plano executado parcialmente em hardware.

Falha em Motor 1/2, horizonte inválido ou impossibilidade física gera `status=blocked`, `execution_allowed=false`, eventos e erro explícito em health, sem comandos executáveis. Solar em cache/fallback ou fallback seguro do solver gera `status=degraded`; falhas de EVSE são igualmente identificadas. Componentes não executados aparecem como skipped. Este é um núcleo de decisão, sem comunicação física com inversor/EVSE: o futuro adaptador de equipamento deve respeitar execution_allowed e gerenciar watchdogs.

## Limites versus energia realizada

Os setpoints individuais são **limites de potência**, não consumo medido. Sua soma é no máximo o bloco e pode ficar abaixo dele quando os EVSEs saturam. A demanda usada nos fluxos é a demanda atual atendível, que pode ser menor que os setpoints. O campo `management.flow_basis` deixa isso explícito. Não se calcula energia fictícia a partir da soma de limites.

Fluxos: solar→prédio/EV/bateria/rede; bateria→prédio/EV; rede→prédio/EV. Rede→bateria não existe nesta política. O runtime informa a demanda não atendida total quando falhas/capacidades dos EVSEs impedem atendê-la. A rede e o SOC devem ser novamente medidos no ciclo seguinte.

## Saída e desempenho

`gie_version`, `decision_time`, `status`, `current_state`, `forecasts`, `management`, `load_balancer`, `flows`, `events`, `health`. Forecasts inclui 48 registros de prédio, EV esperado/Q90, energia, ocupação, chegadas, fila, risco e solar. Management inclui plano integral, primeira decisão planejada/executada e parâmetros físicos.

Health registra os tempos individuais e total, fonte solar, solver/fallback e falhas. O carregamento inicial dos modelos é medido separadamente; em produção eles devem ser reutilizados.

## Demonstração executada

`outputs/gie_runtime/v1/cycle.json` contém a saída completa, sem truncamento. `summary.json`, `forecasts_48.csv`, `mpc_plan_48.csv`, `cycle_flow.png`, testes e manifestos acompanham o resultado.

**Limitação explícita:** os históricos oficiais terminam em junho de 2026 e não existe inversor físico conectado a este teste. O demonstrador reutiliza valores do histórico sintético com deslocamento de semanas completas apenas nas cópias em memória, preservando dia da semana. Os CSVs oficiais e modelos não são alterados. O solar atual de 25 kW, SOC de 50% e quatro EVSEs conectados são fixtures declaradas; prédio e demanda EV atuais vêm do intervalo correspondente do dataset sintético. A meteorologia futura vem da consulta real atual ou de cache válido. Isso comprova integração dos componentes reais; não é avaliação independente de acurácia nem operação física ao vivo.

Executado em 07/09/2026 para decision_time 12:00, com deslocamento de 84 dias a partir de 15/06/2026. Resultado OK, fonte open_meteo, solver ótimo, 48 horários alinhados e 100 testes aprovados. Tempo do ciclo aproximadamente 2,784 s; carregamento inicial separado aproximadamente 0,895 s. Não há otimização prematura ou retreinamento.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/gie_runtime -v
.\.venv\Scripts\python.exe -B src/gie_runtime/demo.py
```

A demonstração faz uma nova consulta e atualiza somente seus próprios artefatos de saída. Preserve uma cópia caso deseje comparar execuções. A revisão do Motor 3 está detalhada em MOTOR3_V1_1_POLICY.md.
