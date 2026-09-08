# Julho 2026 — avaliação temporal congelada

Julho foi gerado após o congelamento da V2. Nenhum treino, ajuste de features, hiperparâmetros, seletor ou previsão foi realizado. O mês é novo temporalmente, mas ainda pertence ao mesmo prédio sintético e EPW típico; não é validação de um prédio real.

Simulação contínua janeiro–julho, com mudança somente na data final. A reexecução divergiu em 56 intervalos de 30/06 (máximo 0,059865 kW), devido à janela periódica de sombreamento limitada pelo fim do RunPeriod. Janeiro–junho original foi preservado exatamente no histórico de avaliação. Detalhes em prefix_comparison.json e model_changes.diff. Mecanismo no [código EnergyPlus 25.2](https://github.com/NatLabRockies/EnergyPlus/blob/v25.2.0/src/EnergyPlus/SolarShading.cc#L8367-L8395).

2.976 timestamps alvo de julho em cada um dos 48 horizontes: 142.848 pares por método. Origens variam por horizonte para avaliar o mês completo; os alvos são os mesmos para todos. As primeiras previsões usam histórico de junho. Durante julho, somente medições já disponíveis entram no histórico; nenhum modelo é atualizado.

| Método | MAE kW | RMSE kW | WAPE % |
|---|---:|---:|---:|
| semana_anterior | 10.941 | 20.885 | 12.602 |
| lightgbm_v1 | 13.202 | 24.167 | 15.206 |
| residual_v2 | 7.333 | 15.242 | 8.446 |
| hibrido | 7.333 | 15.242 | 8.446 |

## Por horizonte

| Minutos | Método | MAE kW | RMSE kW | WAPE % |
|---:|---|---:|---:|---:|
| 15 | semana_anterior | 10.941 | 20.885 | 12.602 |
| 15 | lightgbm_v1 | 6.733 | 12.389 | 7.754 |
| 15 | residual_v2 | 2.184 | 7.330 | 2.516 |
| 15 | hibrido | 2.184 | 7.330 | 2.516 |
| 60 | semana_anterior | 10.941 | 20.885 | 12.602 |
| 60 | lightgbm_v1 | 11.520 | 21.038 | 13.268 |
| 60 | residual_v2 | 4.355 | 10.953 | 5.016 |
| 60 | hibrido | 4.355 | 10.953 | 5.016 |
| 180 | semana_anterior | 10.941 | 20.885 | 12.602 |
| 180 | lightgbm_v1 | 14.222 | 25.440 | 16.381 |
| 180 | residual_v2 | 6.333 | 13.781 | 7.294 |
| 180 | hibrido | 6.333 | 13.781 | 7.294 |
| 360 | semana_anterior | 10.941 | 20.885 | 12.602 |
| 360 | lightgbm_v1 | 13.220 | 24.446 | 15.227 |
| 360 | residual_v2 | 7.958 | 15.805 | 9.165 |
| 360 | hibrido | 7.958 | 15.805 | 9.165 |
| 720 | semana_anterior | 10.941 | 20.885 | 12.602 |
| 720 | lightgbm_v1 | 14.168 | 25.137 | 16.318 |
| 720 | residual_v2 | 9.305 | 17.796 | 10.717 |
| 720 | hibrido | 9.305 | 17.796 | 10.717 |

O seletor congelado escolhe residual V2 nos 48 horizontes; híbrido e residual coincidem. Nenhum método foi selecionado com julho. WAPE usa soma de erros absolutos / soma de consumo real. Pares de previsão se sobrepõem e não são observações independentes.

Os timestamps marcam o início dos intervalos. Origem t significa última medição [t,t+15min), disponível em t+15min. O primeiro alvo começa no instante de emissão.

![Erros](graficos/erro_por_horizonte.png)

![Curvas](graficos/curvas_12h.png)
