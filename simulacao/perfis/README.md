# Novos perfis sintéticos do GIE — datasets V1

Implementação isolada em `C:\goodwill_ai\GIE_DATASETS`, baseada no commit
`50e0d6cba42754c24350da9fd513fce4547f2f39` do GIE oficial. Nenhum arquivo original,
modelo, core, demo, dataset comercial, Backend ou Site foi modificado.

## Conteúdo

- `PREMISSAS.md`: tabela de cargas e cálculos fixados **antes** da simulação.
- `sources.json`: referências oficiais GoodWe e climáticas.
- `loads.py`: equipamentos, horários e eventos domésticos/comerciais; resolução interna1min.
- `build_model.rb`: novos modelos OpenStudio/EnergyPlus, áreas80/150m², alvenaria,
  cobertura isolada, infiltração, ocupantes e climatização de capacidade fixa.
- `ev.py`: eventos, FCFS, espera45min, fila máxima3, indisponibilidade,
  veículo7/11/22kW, capacidade/SOC e taper acima de80%.
- `generate.py`: exportação, PV, manifestos, divisão mensal, plano temporal e gráficos.
- `validate.py`: contratos, física, reconstrução independente e reprodução determinística.
- `run_pipeline.py`: geração completa e validação. Reescreve apenas outputs desses
  dois perfis; não altera os artefatos antigos nem treina modelos.
- `{posto_24h_v1,residencial_v1}/`: parâmetros, tabela de cargas, horários, OSM/IDF e logs.
- `../../data/synthetic_profiles/`: séries anuais/mensais, sessões, manifestos e diagnóstico.

As curvas de consumo das edificações vieram de **execuções reais do EnergyPlus25.2**,
com modelos novos. EV e PV são simulações próprias Python, sem MPC ou controle GIE.
Tudo é **SIMULATED**, incluindo dados de clima derivados de TMY; nada é medição2025.

## Reprodução (Python3.12, OpenStudioSDK3.11, EnergyPlus25.2)

Criar ambiente separado, na raiz desta cópia do GIE:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r simulacao/perfis/requirements.txt
.\.venv\Scripts\python.exe -B simulacao/perfis/run_pipeline.py `
  --openstudio 'C:\openstudioapplication-1.11.1\bin\openstudio.exe' `
  --energyplus 'C:\openstudioapplication-1.11.1\EnergyPlus\energyplus.exe'
```

Os executáveis são argumentos; em Linux usar caminhos equivalentes. O diretório pode
ser movido: OSM/IDF são regenerados para resolver os Schedule:File locais. Os UUIDs
OpenStudio e os logs têm metadados variáveis; as séries numéricas são determinísticas.
`source.zip` guarda o clima original; se ausente, o roteiro baixa a URL registrada e
**exige o mesmo SHA-256**. EPW é anual com calendário típico, remapeado para2025.
Não substituir automaticamente o clima por outra revisão.

Nesta execução foi reutilizado, sem instalação/modificação, o ambiente existente
`C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe`.
O EnergyPlus26.1 instalado separadamente não funcionou; o25.2 incluído no OpenStudio
funcionou e é a versão exigida. Não houve fallback para curva de consumo só em Python.

Validar os arquivos existentes e repetir a simulação térmica em pasta temporária:

```powershell
.\.venv\Scripts\python.exe -B simulacao/perfis/validate.py `
  --energyplus 'C:\openstudioapplication-1.11.1\EnergyPlus\energyplus.exe'
```

Os CSVs usam ponto decimal, vírgula como separador, UTF-8 e timestamps ISO8601 com
UTC−03:00. `manifest.json` identifica estação, seeds, versões, equipamentos e hashes.
`baseline.json` é o registro anterior à geração dos454 arquivos originais.

## Contrato e limites

Leia `CONTRATOS.md` e `../../data/synthetic_profiles/RELATORIO.md` antes de treinamento.
Não carregar esses CSVs nos modelos congelados ou no importador atual do EMPS sem
adaptadores específicos: nomes parecidos não significam compatibilidade.
Não implementar esses adaptadores nem executar treinamento nesta etapa.
