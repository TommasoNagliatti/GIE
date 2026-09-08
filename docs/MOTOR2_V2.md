# Motor 2 V2 — potência híbrida e Q90

Versão separada: não substitui código, modelos ou resultados da V1. Reutiliza os cinco modelos V1, sem retreinamento, e acrescenta um LightGBM global quantílico de potência (`alpha=0.90`). As mesmas 217 features causais são utilizadas.

- Código: `src/motor_carregadores_v2/`.
- Modelos/configuração: `models/carregadores/v2/`, com `power_q90.txt`, `selector.json` e `metadata.json`.
- Dependências preservadas: `models/carregadores/v1/` e `src/motor_carregadores/`; manter ambas as versões ao distribuir o projeto.
- Avaliação: `outputs/motor_carregadores/v2/relatorio_v2.md`.

## Produção

```powershell
.\.venv\Scripts\python.exe -B src\motor_carregadores_v2\predict.py --data data\demanda_carregadores_6_meses.csv --timestamp "2026-06-15 07:45" --output outputs\motor_carregadores\v2\previsao_cli_48.csv
```

Com `src` no PYTHONPATH:

```python
from motor_carregadores_v2.predict import MotorCarregadores
motor = MotorCarregadores()
previsao = motor.predict(historico, timestamp)
```

Retorna 48 linhas com `timestamp_previsto`, `potencia_solicitada_prevista_kw`, `potencia_solicitada_alta_kw`, `energia_solicitada_prevista_kwh`, `carregadores_ocupados_previstos`, `carros_chegando_previstos`, `carros_na_fila_previstos`, `probabilidade_fila`.

O seletor usa exclusivamente o MAE de maio por horizonte. Q90 é treinado em janeiro–abril, com early stopping em maio. A saída alta é `max(pontual, clip(Q90, 0, 88))`; a avaliação separa cobertura do Q90 bruto e da saída operacional. Não se força cobertura de 90% observando junho. A cobertura é marginal por intervalo, não simultânea para uma trajetória inteira de 12h.

Junho é diagnóstico secundário, porque já foi observado na V1 e motivou esta evolução. A V2 permanece congelada após esse diagnóstico. Potência solicitada mantém a definição original: demanda dos veículos conectados, sem incluir a fila.

Histórico mínimo: 2.689 intervalos. A linha t representa a última medição iniciada em t, conhecida em t+15min; o primeiro intervalo previsto começa nesse instante de emissão. As contagens e a probabilidade de fila são retornadas pela própria V1, sem alteração.
