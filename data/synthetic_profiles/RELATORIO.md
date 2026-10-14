# Relatório final — datasets sintéticos GIE V1

**Implementado, executado e validado.** Ano sintético2025,15min,35.040 linhas por
série. Dois modelos novos executados no EnergyPlus25.2/OpenStudio3.11; EV por eventos
Python em1min e PV demonstrativo separado. Nenhum modelo foi treinado.

Trabalho entregue em `C:\goodwill_ai\GIE_DATASETS`, cópia isolada do repositório oficial.
Não foi aplicado ao EMPS em execução. Sem alterações de Backend, Site, App, banco,
MPC, GIEControl, demos, dados comerciais ou modelos congelados. Sem commit/push.

| Resultado anual | POSTO_24H_V1 | RESIDENCIAL_V1 |
|---|---:|---:|
| Edificação, sem EV |85.791,85 kWh|2.794,56 kWh|
| Menor mês da edificação |6.737,19 kWh|218,17 kWh|
| Maior mês da edificação |7.650,00 kWh|245,67 kWh|
| EV AC entregue, contabilizado separado |39.495,74 kWh|756,42 kWh|
| Tentativas/sessões registradas |2.289|42|
| Sessões que conectaram |2.085|42|
| Ocupação média temporal |29,31%|4,10%|
| Quantidade/potência de EVSE |2×22kW|1×7kW|
| PV / inversores |50kWp /2×30kW|5,5kWp /6kW|
| Baterias |BAT_01 e BAT_02 distintas|sem bateria; opção parametrizada|

A residência segue o complemento mais recente: **3–4 recargas mensais**,10–25kWh
solicitados por sessão. A hipótese semanal do pedido inicial não foi utilizada.
Os42 eventos atingiram o alvo, mesmo com a indisponibilidade de120min sobreposta
intencionalmente a uma recarga. Casa doméstica típica, sem carga comercial oculta.

O posto recebeu6,27 tentativas/dia.1.245 sessões atingiram o alvo;840 saíram antes,
203 abandonaram a espera e1 encontrou fila cheia. Energia solicitada não atendida:
12.998,61kWh AC. Isso **não é falha de conservação**: estadias1–4h, aceitação7/11/22kW,
fila e alvos8–40kWh deixam demanda insatisfeita. Não aumentamos artificialmente
potência/permanência para fechar alvos. Há intervalos sem EV, movimentos noturnos,
filas e298 minutos conectados sob manutenção simulada.

## Realismo: esperado versus simulado

As tabelas de equipamentos, potência, frequência e cálculo diário/mensal foram
registradas antes da geração em `../../simulacao/perfis/PREMISSAS.md` e
`load_table.csv` de cada perfil. `expected_vs_simulated.csv`,
`monthly_load_breakdown.csv` e `monthly_validation.csv` mostram os resultados.

- Posto: cargas programadas ficaram próximas do orçamento: refrigeração−1,74%,
  bombas−2,93%, iluminação externa+1,07%, cozinha0%. As diferenças são explicadas
  por temperatura TMY, duração real de noite e eventos intermitentes.
- AC do posto:254–948kWh/mês, abaixo da aproximação inicial20–55kWh/dia no inverno.
  O cálculo térmico prevê menos horas efetivas de compressor em clima ameno,
  apesar da disponibilidade06–23h. Não se substituiu essa demanda por um piso artificial.
- Casa: geladeira−2,90%; chuveiro+0,46%. Ventilador51,68kWh/ano versus95,81kWh
  de referência: o limiar24°C entre17–24h resulta em1,89h/dia, não3,5h presumidas.
  AC do quarto é ocasional:21–24h, noites quentes e escolha de uso65%; vários meses
  não precisam de resfriamento. O total permaneceu218–246kWh/mês sem EV.
- Picos médios de15min:15,50kW no posto e4,23kW na casa. A referência inicial30kW
  para o posto não foi forçada: o conjunto e a simultaneidade modelados não a exigem.
  O chuveiro doméstico é5,5kW instantâneos por7–9min; a média do intervalo de15 minutos é menor.
- Edificação, EV e PV são séries separadas. Não há despacho de baterias, SOC fictício,
  consumo líquido artificial nem controle MPC embutido nos históricos brutos.

## Verificações executadas

**19 testes automatizados aprovados**, cobrindo os dois perfis e casos negativos:
cronologia anual/fuso/disponibilidade; NaN/inf; potência/energia; faixas mensais;
limites EVSE/ocupação; IDs e SOC; reconstrução independente minuto a minuto de
energia, fila, chegadas e conexão; PV/noturno; equipamentos; frequência residencial;
variação diária/semanal/sazonal; recomposição exata dos72 arquivos mensais;
fronteiras dos48 alvos; hashes; reprodução de horários/sessões e execução EPlus.

EnergyPlus repetido em diretórios temporários: os CSVs de clima/estado e medidores
foram **idênticos byte a byte** em cada perfil. O comando completo de reprodução foi
executado com sucesso; evidências em `validation_report.json` e nos logs da simulação.
Os dois painéis de diagnóstico e o gráfico de escalas foram inspecionados visualmente.

A primeira simulação do posto apontou vazão inadequada para a serpentina DX;
corrigida de1,1 para0,8m³/s no modelo novo, seguida de nova execução. A exportação
EPlus teve horário de fim do intervalo convertido para início, incluindo24:00.
A validação também distingue fuso IANA de offset UTC equivalente.

## Preservação e limitações

454 arquivos originais comparados com SHA-256 anterior: **nenhum alterado**.
O manifesto congelado antigo possui221 entradas; há uma divergência **preexistente**
em `demo/high_autonomy_v2/app.py`. O hash inicial/final é o mesmo; não corrigimos
nem atualizamos cegamente o manifesto. Detalhes em `preservation.json`.

Clima TMY regional, não observado2025; geometrias/tabelas demonstrativas não calibradas
em campo. A residência usa duas zonas térmicas simplificadas60/20m², não planta
arquitetônica detalhada. Loja150m²; PV de50kWp pressupõe área adicional de cobertura
no pátio/canopy, além da loja. Refrigeração é carga elétrica por ciclos e fração de
calor rejeitado; não é modelo termodinâmico de cada freezer. Bombas não modelam
hidráulica. Não há aquecimento de ambientes; temperaturas livres no inverno são
possíveis. Não se afirma conforto térmico garantido.

Avisos residuais: um aviso EnergyPlus por perfil de carga de dimensionamento de
**aquecimento zero**, coerente com ausência de aquecimento. Nenhum severe/fatal.
OpenStudio avisa que não lê o bloco de condições de projeto de81 campos do EPW;
usamos os dias de projeto doDDY. ODDY também referencia chuva não usada nesses
modelos, e o tradutor a avisa como ausente. A parede compartilhada da residência
recebe automaticamente construção reversa. Esses avisos constam dos logs, não
foram ocultados; as séries anuais e o balanço foram verificados.

PV é aproximação horizontal sem sombras locais. Baterias individuais estão
parametrizadas, mas não houve despacho/controle/validação deSOC ao longo do tempo.
O limite opcional residencial2,2kW AC também considera a eficiência de descarga
antes da verificação de corrente DC mínima. Equipamentos GoodWe são referências
de catálogo; instalação, proteções, firmware e homologação regional permanecem futuros.

Os modelos atuais e o importador EMPS **não aceitam diretamente estes dados**.
Arquivos mensais resolvem tamanho; não corrigem schema ou proveniência. Não trocar
SIMULATED por IMPORTED/MEASURED. Clima horário requer respeitar `weather_available_at`
para não usar futuro inadvertidamente. Detalhes em `../../simulacao/perfis/CONTRATOS.md`.

## Arquivos e próximos passos

Novos arquivos somente em `simulacao/perfis/` e `data/synthetic_profiles/`.
Nenhum arquivo original alterado/removido. Inventário e hashes em `created_files.json`.
`git status --short` mostra apenas esses dois diretórios novos;
`git diff --stat` está vazio porque não há alteração em arquivos já versionados.

Reprodução: ver `../../simulacao/perfis/README.md`. Scripts e outputs anuais/mensais,
OSM/IDF, EPW original, tabelas, parâmetros, eventos, manifestos e gráficos estão locais.
Resultados executados/validados; não há bloqueio para esta entrega de datasets.
Próxima etapa: revisão das hipóteses com dados reais, adaptação explícita dos schemas
e treinamento separado por estação, mantendo o teste final reservado. Multiestação,
MPC novo e integração EMPS continuam fora do escopo.
