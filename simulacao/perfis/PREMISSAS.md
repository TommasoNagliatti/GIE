# Premissas fixadas antes da geração — V1 / calendário sintético 2025

Origem SIMULATED. Não são medições nem projeto elétrico. Ambos usam TMYx São Carlos
2011–2025 como proxy regional de Itirapina/SP; o ano 2025 apenas define o calendário.
Sem normalização posterior das curvas para atingir metas de consumo.

## Residência: 80 m², três moradores, quarto climatizado de 20 m²

| Carga | Potência ativa kW | Utilização / ciclo | kWh/dia esperados | kWh/30 dias |
|---|---:|---|---:|---:|
| Geladeira | 0,14 | 35–55% do tempo, ciclos de 40 min dependentes da temperatura | 1,51 | 45,36 |
| Standby / roteador | 0,035 | 24 h | 0,84 | 25,20 |
| Iluminação | 0,22 | 5 h equivalentes, manhã e noite; variação ocupação | 1,10 | 33,00 |
| TV e eletrônicos | 0,18 | 4 h úteis / 5 h fim de semana | 0,77 | 23,14 |
| Ventilador | 0,075 | 0–7 h; temperatura >24°C | 0,26 | 7,80 |
| Lavadora | 0,45 | 55 min; 3 dias/semana | 0,18 | 5,30 |
| Cozinha (microondas/cafeteira) | 1,20 | 27 min/dia, em três eventos | 0,54 | 16,20 |
| Chuveiro elétrico | 5,50 | três banhos de 8 min/dia; sem simultaneidade | 2,20 | 66,00 |
| Outros eletrodomésticos | 0,35 | 1 h/dia | 0,35 | 10,50 |
| AC quarto + ventilador interno | até ~0,95 | condicionado à temperatura, 21–24 h, parte dos dias; COP3,2 | 0–1,50 | 0–45 |

Base central sem AC: **7,76 kWh/dia / 232,5 kWh em 30 dias**.
Faixa de aceitação mensal da edificação: 180–450 kWh, sem EV nem PV.
O chuveiro tem potência instantânea 5,5 kW mas os 15 minutos exibem a média;
não impor pico artificial de 6 kW se houver simultaneidade doméstica física.
EV: **3–4 sessões/mês**, 10–25 kWh AC solicitados/sessão, EVSE7kW.
O complemento mais recente prevalece sobre a hipótese semanal do texto original.

## Posto: loja 150 m², funcionamento 24 horas

| Carga | Potência ativa kW | Utilização / ciclo | kWh/dia esperados | kWh/30 dias |
|---|---:|---|---:|---:|
| Refrigeração comercial | 5 (10 compressores de 0,5) | 60–85% conforme clima; fases distintas | 84,00 | 2520,00 |
| Luz interna | 1,20 | 24 h | 28,80 | 864,00 |
| Luz externa | 2,60 | noite (GHI<20), referência 12 h | 31,20 | 936,00 |
| Caixas/rede/computadores | 0,60 | 24 h | 14,40 | 432,00 |
| Bombas de combustível | 4,40 (4×1,10) | eventos de 3 min, ~8 eventos/h/bomba dia, ~2 noite; variação semanal | 36,96 | 1108,80 |
| Cozinha / estufa / café | 2,40 | 8 h equivalentes em horário comercial | 19,20 | 576,00 |
| Compressor auxiliar | 1,50 | ciclos de 3 min a cada 45 min, 06–22 h | 1,60 | 48,00 |
| AC + ventilação | até ~5,30 | COP3,2, setpoint24°C, 06–23 h, demanda térmica calculada | 20–55 | 600–1650 |

Base sem AC: **216,16 kWh/dia / 6484,8 kWh em 30 dias**; com AC,
expectativa inicial 7085–8135 kWh/30 dias. Faixa de aceitação mensal:6000–13000.
A faixa inicial 8–18 kW é uma referência operacional, não carga-base constante.
Bombas, compressor e cozinha não operam todos continuamente; não somar placas.
EV: 6 chegadas/dia em média antes dos fatores semanais, 2×22kW AC,
veículos aceitam7/11/22kW, estadias de 1–4 h, fila máxima3, espera até45min.
Clima/ocupação afetam horários, não multiplicam arbitrariamente o total mensal.

## Equipamentos e fronteira de energia

Posto: PV50kWp em dois blocos25kWp, cada um ligado a um GW30K-ET (30kW AC).
BAT_01 e BAT_02 são GW61.4-BAT-AC-G10 independentes, um por inversor.
61,4kWh nominais / 60kWh úteis de catálogo; faixa de tensão275,52–346,56V.
Limite conservador adotado12kW/bateria, inferior a275,52V×50A=13,776kW
na entrada escolhida do ET. PV+bateria devem compartilhar30kW por inversor.
Não representar o conjunto como bateria única e não simular despacho/SOC temporal.
SOC inicial50%, faixa20–95%, eficiências de carga/descarga0,95 são hipóteses.
Rede: importação90kW/exportação60kW, hipótese demonstrativa, não homologação.

Casa: PV5,5kWp / GW6000-ES-20 (ES G2)6kW AC; EVSE GW7K-HCA-20.
Baterias padrão: array vazio. Opção separada LX U5.4-20, 5,4kWh, 50A,
2,2kW AC conservadores (mínimo47,5V), sem série SOC; não associar à versão M.
Rede: importação17kW/exportação6kW. Pode complementar a recarga além do solar.

PV: proxy explícito de módulos horizontais, GHI horário conservado por 4 intervalos,
NOCT45°C, coeficiente -0,0035/°C, perdas14%, conversão97%. Não é Solar Forecast,
projeto de strings ou medição. Não representa sombreamento local nem despacho.

Fontes oficiais e clima constam em sources.json. Compatibilidade aqui é de envelope
nominal; homologação regional, cabos, proteções e firmware exigem projeto futuro.
