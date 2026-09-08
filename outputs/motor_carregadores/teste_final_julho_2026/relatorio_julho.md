# Motor 2 V2 — teste temporal final de julho de 2026

Julho é uma extensão sintética do cenário, com fator mensal 1,03 e deslocamento −0,03 hora herdados de junho por autorização e pré-registro anteriores à geração. Todas as demais regras foram mantidas. Janeiro–junho agregado e sessões foram reproduzidos byte a byte; originais preservados.

2.976 timestamps alvo de julho por horizonte, 142.848 pares sobrepostos por método. Observações entram no histórico somente quando disponíveis. Modelos, features, seletor, Q90 e threshold congelados; nenhum ajuste ou calibração. Teste temporal novo do mesmo simulador, não validação em dados reais.

| Método | MAE kW | RMSE kW | WAPE % |
|---|---:|---:|---:|
| media_4semanas | 5.826 | 9.767 | 53.77 |
| residual_v1 | 5.586 | 9.224 | 51.56 |
| hibrido_v2 | 5.504 | 9.159 | 50.80 |

| Minutos | Método | MAE kW | RMSE kW | WAPE % |
|---:|---|---:|---:|---:|
| 15 | media_4semanas | 5.826 | 9.767 | 53.77 |
| 15 | residual_v1 | 5.574 | 9.221 | 51.45 |
| 15 | hibrido_v2 | 2.595 | 5.612 | 23.95 |
| 60 | media_4semanas | 5.826 | 9.767 | 53.77 |
| 60 | residual_v1 | 5.584 | 9.231 | 51.54 |
| 60 | hibrido_v2 | 5.584 | 9.231 | 51.54 |
| 180 | media_4semanas | 5.826 | 9.767 | 53.77 |
| 180 | residual_v1 | 5.585 | 9.231 | 51.54 |
| 180 | hibrido_v2 | 5.585 | 9.231 | 51.54 |
| 360 | media_4semanas | 5.826 | 9.767 | 53.77 |
| 360 | residual_v1 | 5.572 | 9.208 | 51.42 |
| 360 | hibrido_v2 | 5.572 | 9.208 | 51.42 |
| 720 | media_4semanas | 5.826 | 9.767 | 53.77 |
| 720 | residual_v1 | 5.609 | 9.238 | 51.77 |
| 720 | hibrido_v2 | 5.609 | 9.238 | 51.77 |

| Contagem | MAE | RMSE |
|---|---:|---:|
| occupancy | 0.415 | 0.660 |
| arrivals | 0.283 | 0.519 |
| queue | 0.301 | 0.599 |

Risco: PR-AUC 0.8046, ROC-AUC 0.9515, Brier 0.0715, Precision 0.5841, Recall 0.9814, F1 0.7323. Threshold original 0.16.

Cobertura alta operacional: 91.27%; Q90 bruto limitado: 91.12%. Cobertura marginal por intervalo, não garantia simultânea para as 12h. Potência solicitada exclui veículos na fila. PR-AUC trapezoidal; AP também em metrics_risk.json.

![Erros](graficos/erro_horizonte.png)

![Potência](graficos/potencia_12h.png)

![Contagens e risco](graficos/contagens_risco.png)
