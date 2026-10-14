# Matriz e formulação pré-implementação — Energy V3

| Restrição anterior | Reutilização / generalização |
|---|---|
| 48×15min; aplicar primeiro passo | Preservada |
| SOC único / capacidade agregada | Substituída por E[i,t], SOC/limites/eficiências individuais |
| 4 EVSEs de 22kW / 88kW | Variáveis por EVSE, limite de veículo e circuitos configurados |
| Solar obrigatoriamente usado | PV usado + corte = PV disponível, por inversor |
| Rede import/export com limites | Preservada como conceito; binária elimina simultaneidade |
| LP / desempate V2 | Novo MILP e política lexicográfica independente |
| Carga/descarga | Binária global por passo: também impede transferência artificial entre baterias |
| Forecast EV como demanda | Primeiro passo usa current; casa usa envelope conservador diagnosticado |
| SOC descartado após reinício | Novo checkpoint simulado atômico, hash de configuração, último ciclo |
| Transportes físicos | Continuam ausentes; physical_dispatch=false |

Variáveis em kW: importação, exportação, PV usado por inversor, carga/descarga por bateria, EV atendido por conector. Energia de bateria em kWh ao fim de cada intervalo. Binárias para direção da rede, direção do banco (sem agregação dos estados) e admissão de EVSE com mínimo técnico.

Balanço AC rígido: PV + import + discharge = building + EV + charge + export. Sem variável de carga obrigatória não atendida: inviável significa decisão bloqueada, não serviço fictício. Evolução individual E_next=E_prev+0,25*(eta_c*C-D/eta_d). SOC e potência limitados. Grupo inversor impõe PV+D+C<=ac_kw como envelope conservador demonstrativo, além do limite documentado PV+D. Não é afirmação de topologia/firmware GoodWe real. Circuitos de EVSE impõem soma dos setpoints <= limite configurado.

Política `solar_only_lex_v3.0`: segurança/edificação rígidas; maximizar EV total 12h e depois EV imediato; minimizar importação 12h e depois imediata (evita adiamento repetido em horizonte móvel); minimizar corte solar; minimizar throughput de baterias/rede. Não usa preços fictícios. Baterias não exportam (descarga <= carga local) e nenhum carregamento pela rede é autorizado por padrão. `grid_allowed_lex_v3.0` é opção explícita, somente fixtures quando selecionada.

Solver SciPy/HiGHS MILP, solução ótima exigida em cada estágio; timeout/falha bloqueia. Cada ótimo é preservado dentro de tolerância numérica documentada. Guarda independente verifica todos os 48 passos antes de aplicar o primeiro. Load Balancer novo conserva o total viável do MPC e busca max-min entre EVSEs admitidos; mínimos técnicos podem exigir suspensão e alternância de admissão.

PV futuro: baseline causal do dia anterior nos mesmos intervalos (sem TMY futuro); primeiro passo usa observação simulada separada. Modelos Fase 2 permanecem congelados; energia/solar futuros do CSV não entram como previsão perfeita. Perfis: BAT_01/BAT_02 61,4kWh cada, 12kW, eta0,95, SOC20–95%, inicial50%; posto rede90/60kW, dois inversores30kW e PV50kWp. Casa sem bateria, rede17/6kW, inversor6kW/PV5,5kWp, EV7kW. Todos os valores vêm dos manifestos e são hipóteses simuladas, não homologação.

## Ajuste numérico observado na validação

O primeiro ensaio de 24h encontrou inviabilidade numérica no último estágio com locks de objetivo 1e-7 kWh. Os locks passaram a 1e-5 kWh (0,01Wh), equivalentes a 4e-5 kW no objetivo imediato. A guarda física continua em 2e-5, sem alterar capacidades/balanços/SOC. Nenhuma solução bloqueada é aplicada. O log da tentativa foi preservado e as 192 otimizações finais passaram.
