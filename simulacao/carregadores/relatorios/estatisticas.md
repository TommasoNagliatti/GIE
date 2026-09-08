# Estatísticas — carregadores AC

Seed: 20260905. Período: 2026-01-01 00:00:00 a 2026-06-30 23:45:00, inícios de intervalos de 15 minutos (UTC−3).

| Indicador | Valor |
|---|---:|
| Registros agregados | 17376.00 |
| Tentativas de uso | 5477.00 |
| Sessões conectadas | 2917.00 |
| Não conectadas | 2560.00 |
| Sessões conectadas por dia | 16.12 |
| Máximo simultâneo carregando | 4.00 |
| Ocupação média temporal (%) | 38.03 |
| Fila média temporal (veículos) | 0.28 |
| Fila máxima (veículos) | 3.00 |
| Intervalos com fila (%) | 19.60 |
| Intervalos com todos ocupados em algum minuto (%) | 27.75 |
| Intervalos com todos ocupados durante os 15 min (%) | 21.89 |
| Potência média (kW) | 10.61 |
| Máximo médio de 15 min (kW) | 75.77 |
| Máximo de 1 min (kW) | 75.77 |
| Energia entregue (kWh) | 46082.44 |

## Distribuição de chegadas por intervalo

| Chegadas | Intervalos | Percentual |
|---|---:|---:|
| 0 | 13769 | 79.241% |
| 1 | 2327 | 13.392% |
| 2 | 852 | 4.903% |
| 3 | 297 | 1.709% |
| 4 | 104 | 0.599% |
| 5 | 23 | 0.132% |
| 6 | 4 | 0.023% |

## Duração de conexão das sessões atendidas

| Faixa | Sessões | Percentual |
|---|---:|---:|
| 1-29 min (espera/corte) | 157 | 5.38% |
| 30-60 min | 653 | 22.39% |
| 61-180 min | 1584 | 54.30% |
| 181-239 min | 10 | 0.34% |
| 240 min ou mais | 513 | 17.59% |

## Dias úteis e finais de semana

| Tipo | Chegadas/dia | Conectadas/dia | Ocupação média | Potência média |
|---|---:|---:|---:|---:|
| dias_uteis | 39.71 | 20.02 | 47.64% | 13.19 kW |
| finais_de_semana | 6.81 | 6.44 | 14.20% | 4.20 kW |

## Chegadas por hora

| Hora | Média de chegadas por hora por dia, incluindo dias com zero |
|---|---:|
| 00h | 0.000 |
| 01h | 0.000 |
| 02h | 0.000 |
| 03h | 0.000 |
| 04h | 0.000 |
| 05h | 0.000 |
| 06h | 0.552 |
| 07h | 3.895 |
| 08h | 6.182 |
| 09h | 2.934 |
| 10h | 1.409 |
| 11h | 1.392 |
| 12h | 1.326 |
| 13h | 1.901 |
| 14h | 3.232 |
| 15h | 3.337 |
| 16h | 1.934 |
| 17h | 1.088 |
| 18h | 0.751 |
| 19h | 0.326 |
| 20h | 0.000 |
| 21h | 0.000 |
| 22h | 0.000 |
| 23h | 0.000 |

## Fila por hora

| Hora | Fila média temporal | Fila máxima | Intervalos com fila (%) |
|---|---:|---:|---:|
| 00h | 0.000 | 0 | 0.00 |
| 01h | 0.000 | 0 | 0.00 |
| 02h | 0.000 | 0 | 0.00 |
| 03h | 0.000 | 0 | 0.00 |
| 04h | 0.000 | 0 | 0.00 |
| 05h | 0.000 | 0 | 0.00 |
| 06h | 0.000 | 0 | 0.00 |
| 07h | 0.291 | 3 | 21.27 |
| 08h | 1.444 | 3 | 66.99 |
| 09h | 0.988 | 3 | 62.43 |
| 10h | 0.424 | 3 | 39.36 |
| 11h | 0.374 | 3 | 34.53 |
| 12h | 0.370 | 3 | 32.04 |
| 13h | 0.357 | 3 | 31.63 |
| 14h | 0.652 | 3 | 45.86 |
| 15h | 0.866 | 3 | 54.42 |
| 16h | 0.510 | 3 | 42.96 |
| 17h | 0.216 | 3 | 21.41 |
| 18h | 0.110 | 3 | 12.98 |
| 19h | 0.041 | 3 | 4.28 |
| 20h | 0.000 | 1 | 0.14 |
| 21h | 0.000 | 0 | 0.00 |
| 22h | 0.000 | 0 | 0.00 |
| 23h | 0.000 | 0 | 0.00 |

## Verificações

Capacidade, fila, nao sobreposicao, conservacao energia, ocupacao reconstruida, timestamps e ausencia de nulos no agregado: OK

Reprodutibilidade verificada em duas execuções: True.

Potências são médias temporais; a ocupação média utiliza minutos conectados, não a média dos máximos de cada intervalo.
Dados sintéticos, sem calibração em sessões reais. Feriados não modelados. Detalhes e dicionário no README.
