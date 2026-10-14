# Contratos dos novos datasets e compatibilidade futura

## Dados e unidades

Em `data/synthetic_profiles/<perfil>/`, cada uma das três séries `building.csv`,
`ev.csv`, `energy.csv` tem35.040 intervalos de15min em2025. `station_id` e
`origin=SIMULATED` acompanham cada linha. `timestamp` é início e `available_at`
é fim do intervalo; integração: **kWh = kW médio ×0,25h**. Não há junção entre estações.

| Arquivo | Conteúdo | Observação |
|---|---|---|
| building.csv | consumo_predio_kw/kwh, temperatura_externa_c, umidade_relativa_pct; submedidores e temperaturas de zonas | Consumo bruto da edificação, sem EV/PV/bateria; Joules EPlus/3.600.000 |
| ev.csv | potência solicitada/entregue, contagens, ocupação, energia e potência/disponibilidade por EVSE | Potências médias; contagens máximas simultâneas; chegadas somadas |
| sessions.csv | chegada/início/fim/desconexão lógica, SOC, capacidade, energia AC, limite veículo, espera e motivo | Uma linha por tentativa; sem conexão: evse/inicio vazios, start_minute=-1 |
| energy.csv | GHI, PV DC disponível, PV AC e clipping, disponibilidade EVSE/inversores/baterias/rede | Entrada física demonstrativa, **sem despacho** e sem SOC temporal |
| equipment_events.csv | manutenção simulada com início/fim e EVSE | Interrompe potência, mas não libera vaga ocupada automaticamente |
| manifest.json | parâmetros individuais, fontes, seeds, versões, hashes e limites compartilhados | Duas baterias no posto; array vazio + opção na casa |
| monthly/ |36 arquivos: três séries ×12 meses | Partes exatas das séries anuais; menos de10.000 linhas e8MiB cada |
| training_split_plan.csv | emissão, fim do último alvo, partição e máscaras | Planejamento apenas; não contém features/treinamento |

`consumo_predio_kwh` NÃO é consumo líquido da rede. `pv_generation_ac_kw` é geração
potencial disponível antes de despacho/curtailment por exportação. Não somar PV como
carga nem deduzir automaticamente da demanda da edificação.

`energia_entregue_kwh` é AC medida no ponto de recarga simulado; ganho no veículo=
0,92×AC. `requested_ac_kwh` usa a mesma fronteira. SOC é fração0–1, limitado pela
capacidade e SOC-alvo. Potência solicitada só inclui veículos conectados; energia
não atendida de fila/rejeição consta de sessões, não da potência de conectados.
O veículo reduz aceitação acima de80%SOC. Conexão permanece até saída, mesmo com
carga concluída; `fim_carga` distingue último minuto energizado de `termino`.

Ocupação é pico simultâneo dentro de15min: `ocupacao_pct=100×ocupados/N`, N=2 ou1.
`ocupacao_media_pct` deriva dos minutos ocupados, adequada à taxa anual. Pode haver
um EVSE ocupado e potência zero (carga concluída, indisponibilidade). Datas de
sessão/ocupação são intervalos `[início,fim)`. Não existe dupla ocupação no mesmo EVSE.

Falhas dos EVSEs são planejadas por seed (quatro eventos/EVSE/ano). Na casa, uma falha
é deliberadamente sobreposta a uma recarga para exercitar a semântica, e isso está
explicitado no código. Baterias, inversores e rede permanecem disponíveis neste V1.

## Clima, solar e disponibilidade causal

TMYx São Carlos2011–2025 é proxy regional de Itirapina, não meteorologia observada
em2025 nem previsão disponível antecipadamente. EnergyPlus interpola temperatura e
umidade para os subintervalos; irradiância horária é mantida em quatro intervalos,
preservando energia horária. PV é aproximação horizontal NOCT, não pvlib/EPlusPV,
não avalia strings, orientação inclinada, sombras nem perdas regionais calibradas.

A fonte meteorológica horária fica disponível em `weather_available_at` (fim da
hora). **Não usar automaticamente clima da mesma linha quando esse horário for
posterior à emissão.** Fazer junção causal por disponibilidade ou lag conservador
≥1h. Nunca usar o TMY futuro como forecast perfeito no treinamento/validação.
Para futuras previsões meteorológicas, usar apenas versões emitidas antes da emissão.

A energia simulada do intervalo fica disponível no fim dos15min; valores futuros
existem no arquivo para construir alvos, não para features. Os intervalos finais
2025-12-31 23:45 terminam2026-01-01 00:00, corretamente.

## Separação para treinamento futuro — nenhum modelo treinado aqui

Treino: janeiro–agosto. Validação: setembro–outubro. Teste: novembro–dezembro.
Na linha iniciada em`t`, observar o intervalo atual só em`t+15min`; os48 alvos são
os próximos48 intervalos, terminando em`t+49×15min`. Excluir48 origens no fim de
cada partição; o alvo final pode terminar exatamente na fronteira exclusiva.

O plano marca2688 intervalos iniciais sem história suficiente para os lags longos
do Motor2 (2689 amostras contando a corrente). Para Motor1 usar sua própria janela
mínima. Validação/teste podem usar histórico passado de partições anteriores da
**mesma estação**, nunca alvos futuros. Rolling stats devem ser trailing, nunca
centralizados; transformadores/scalers/seleção ajustados apenas no treino.
Teste final reservado, sem ajuste de hiperparâmetros ou escolha de políticas.

## Incompatibilidades auditadas

- Motor1: nomes principais semanticamente próximos, mas loaders exigem tempo naive
  e matrizes numéricas. Remover metadados somente via adaptador explícito, converter
  timezone para horário local antes de retirar tz. Não inferir UTC de tempo naive.
- Motor1 original usa edificação comercial muito maior e partições2026. Novo consumo,
  clima e horizonte exigem avaliação e treinamento específicos, não escala artificial.
- Motor2 V1/V2: limites88kW, quatroEVSEs,25%/EVSE, máximos de contagens e calendário2026
  são específicos do comercial. Novos perfis têm44/7kW e50/100% porEVSE. Não inventar
  dois/três EVSEs extras, não aplicar modelos congelados nem seus clips.
- O runtime atual possui estado agregado e não controla BAT_01/BAT_02 individualmente.
  Aqui são identidades e restrições documentadas; nenhum multiestação/MPC foi criado.
- EMPS consultado apenas em `docs/GIE_V2_HANDOFF.md`, `docs/EMPS_V2_ARCHITECTURE.md`
  e contrato de importação: aceita colunas canônicas inglesas, rejeita extras e gera
  origem **IMPORTED**. Não mandar estes CSVs diretamente nem trocar SIMULATED por
  IMPORTED. Fracionamento mensal atende tamanho, não resolve schema/proveniência.
- Mapeamento futuro: consumo_predio_kw→building_power_kw;
  temperatura_externa_c→outside_temperature_c;
  umidade_relativa_pct→relative_humidity_percent. Demais campos/identidade/proveniência
  requerem revisão explícita do contrato. Nenhum endpoint/importação foi implementado.

As fontes e os limites nominais GoodWe constam do manifesto. As potências de bateria
são referência AC; descarga DC=potênciaAC/eficiência. Limite conjunto PV+bateria por
inversor deve ser aplicado em futuro despacho. Nenhuma demonstração de autonomia,
fatura, atendimento garantido, instalação homologada ou desempenho ML é inferida.
