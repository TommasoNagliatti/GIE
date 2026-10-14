# Previsores por estação — v1

Entrega experimental offline, exclusivamente com dados sintéticos. Não instala serviço, não altera runtime nem seleciona modelos comerciais.

## Ambiente e execução
Python 3.12. Ambiente utilizado: `C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe`.
Para outro computador, crie um venv isolado e instale `src/station_forecasts/requirements.txt`; não instale globalmente.
Na raiz da cópia de trabalho, em PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m unittest station_forecasts.test_contracts -v
```

Para REPRODUZIR o treinamento, use uma cópia separada nova contendo `src/station_forecasts`, `data/synthetic_profiles` e `reports/station_forecasts/v1/PROTOCOL.md`, nos mesmos caminhos relativos. Não copie modelos/relatórios de resultados para essa nova cópia; não remova os artefatos entregues. Execute na raiz dessa cópia:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m station_forecasts.train --profile posto_24h_v1
python -B -m station_forecasts.train --profile residencial_v1
python -B -m station_forecasts.evaluate --station DEMO_POSTO_24H_001
python -B -m station_forecasts.evaluate --station DEMO_CASA_001
```

Treinamento recusa pasta de modelo existente; avaliação recusa teste já concluído. Os relatórios desta implementação usam `v1` fixo: novos experimentos devem usar outra cópia, não apenas `--version`. O teste de preservação requer a cópia completa e `preservation_before.json`; não é aplicável à cópia mínima de reprodução. Seeds e número de threads são fixos; horários e hashes dos metadados não serão iguais entre execuções. Foi comprovada igualdade exata do modelo building_15 retreinado para ambas as estações; não se afirma retreinamento integral duplicado de todos os heads.

## Inferência

```python
import pandas as pd
from station_forecasts.predict import Forecaster
model = Forecaster('DEMO_CASA_001')
b = pd.read_csv('data/synthetic_profiles/residencial_v1/building.csv')
e = pd.read_csv('data/synthetic_profiles/residencial_v1/ev.csv')
issue = pd.Timestamp('2025-10-01T12:00:00-03:00')
b = b.loc[pd.to_datetime(b['timestamp']) < issue].tail(2689)
e = e.loc[pd.to_datetime(e['timestamp']) < issue].tail(2689)
forecast = model.predict(b, e, issue)
assert len(forecast) == 48
```

Último intervalo observado termina em `issue`; primeira previsão inicia em `issue` e a última termina 12h depois. Timestamps exigem offset e são convertidos explicitamente para America/Sao_Paulo. Histórico contínuo mínimo: 2689 intervalos. Futuros, lacunas, mistura de estações, NaN, limites inválidos e histórico desatualizado são recusados.

Saídas: `timestamp_previsto`, `consumo_previsto_kw`, `potencia_solicitada_prevista_kw`, `potencia_solicitada_alta_kw`, `energia_solicitada_prevista_kwh`, `carregadores_ocupados_previstos`, `carros_chegando_previstos`, `carros_na_fila_previstos`, `probabilidade_fila`. Campos adicionais explícitos em emps-forecast-v1: `probabilidade_recarga` e `potencia_q90_bruta_kw`. Contagens são expectativas fracionárias, não eventos inteiros. Energia = potência solicitada × 0,25h; não é energia efetivamente entregue. Potência alta = máximo entre ponto e Q90 bruto; não é garantia de atendimento nem quantil recalibrado.

Configuração JSON (`--config`) aceita estação, perfil, caminho dos dados, períodos, timezone/localização, EVSEs e limites. v1 exige 48 passos de 15 minutos e histórico compatível; não promete suporte arbitrário a outras resoluções. Features float32 estão ordenadas em metadata.json e feature_schema.json. Forecaster carrega por station_id/version e verifica hashes dos artefatos; não implementa serviço multiestação.

## Causalidade e auditoria
Pipelines antigos usavam datas de 2026, quatro EVSEs de 22kW e 88kW agregados. Os novos usam 2025 e configurações independentes: posto 2×22kW; casa 1×7kW. Edificação, potência solicitada, potência entregue, ocupação, chegadas e fila permanecem semanticamente separados. Solar e baterias não viram alvos de previsão de consumo. Não há alteração no despacho.

`available_at` é fim do intervalo. Clima observado só entra quando `weather_available_at <= issue`; não se usa TMY futuro como previsão meteorológica. Calendário futuro é conhecido; lags e médias são retrospectivos. O treino lê somente arquivos mensais até outubro; novembro/dezembro são abertos pela avaliação após congelamento. Origens finais são expurgadas para não atravessar fronteiras. Todos os 48 horizontes são avaliados; janelas sobrepostas não são observações independentes.

Consulte `reports/station_forecasts/v1/RELATORIO_FINAL.md`, métricas por horizonte e diagnósticos por sessão antes de integrar. Especialmente o Motor 2 residencial não está validado para decisões autônomas.
