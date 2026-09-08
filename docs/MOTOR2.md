# Motor 2 V1 — demanda dos carregadores

Cinco modelos LightGBM globais compartilham 48 horizontes: potência residual, ocupação Poisson, chegadas Poisson, fila Poisson e probabilidade de fila binária. As contagens previstas são expectativas fracionárias.

## Arquivos

- `src/motor_carregadores/features.py`: features atuais, lags até 28 dias, janelas históricas e calendário do alvo.
- `train.py`: treino janeiro–abril e early stopping/threshold em maio; recusa sobrescrever modelos existentes.
- `evaluate.py`: avaliação de junho após congelamento; recusa repetir uma avaliação concluída.
- `predict.py`: produção, sem treino. Classe `MotorCarregadores` reutiliza os cinco modelos.
- `models/carregadores/v1/`: cinco modelos, `config.json` e `metadata.json`.
- `outputs/motor_carregadores/v1/`: auditoria, métricas, previsões, gráficos e evidências de preservação.

## Produção

No terminal do VS Code aberto em GIE:

```powershell
.\.venv\Scripts\python.exe -B src\motor_carregadores\predict.py --data data\demanda_carregadores_6_meses.csv --timestamp "2026-06-15 07:45" --output outputs\motor_carregadores\v1\previsao_cli_48.csv
```

Com `src` no PYTHONPATH:

```python
import pandas as pd
from motor_carregadores.predict import MotorCarregadores

motor = MotorCarregadores()
historico = pd.read_csv("data/demanda_carregadores_6_meses.csv")
previsao = motor.predict(historico, "2026-06-15 07:45")
```

A função descarta as linhas futuras antes de validar e construir features. Exige 2.689 linhas contínuas (28 dias mais o intervalo atual). Cada timestamp marca o início do intervalo observado: a linha 07:45 está disponível às 08:00; as 48 previsões cobrem os intervalos iniciados às 08:00 até 19:45.

Saída: `timestamp_previsto`, `potencia_solicitada_prevista_kw`, `energia_solicitada_prevista_kwh`, `carregadores_ocupados_previstos`, `carros_chegando_previstos`, `carros_na_fila_previstos`, `probabilidade_fila`. Energia é potência média multiplicada por 0,25 h. O threshold de maio serve para avaliar/classificar risco, sem modificar a probabilidade retornada.

## Definições e limites

O dataset define potência solicitada como média da demanda dos veículos conectados com energia pendente. Não inclui fila nem veículos que abandonaram. Portanto, este alvo ainda não representa toda a demanda não atendida de um futuro sistema com controle de potência. Ocupação e fila são máximos observados no intervalo, não médias temporais. Limites de saída: 88 kW, ocupação 4, chegadas 6, fila 3, probabilidade 0–1.

Janeiro–abril: treino; maio: early stopping e threshold; junho: teste do Motor 2, sem decisões posteriores. Os primeiros 28 dias são contexto; as últimas 48 origens de cada partição são excluídas para não cruzar fronteiras com os alvos. O conjunto completo já foi inspecionado ao gerar os dados sintéticos; junho é reservado ao desenvolvimento deste motor, não um teste real totalmente inédito.

Não executar treino para prever. Dependências já disponíveis no `.venv`; nenhuma alteração ao Motor 1 ou aos CSVs oficiais.
