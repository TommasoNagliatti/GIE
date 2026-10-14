# GIE multiestação V3 — publicação das Fases 1–5.5

Esta branch adiciona os perfis sintéticos residencial e posto 24 h, modelos treinados por estação, Energy V3 com MPC multibateria, cadastro de estações sem histórico, painel e avisos, e comparação residencial sem/com bateria. O GIE comercial, High Autonomy V2, modelos congelados, 16 cenas e demonstrações permanecem no histórico original da `main`; esta branch apenas acrescenta os novos módulos e a referência portátil do launcher ao original versionado.

## Uso local no Windows

Requer Python 3.12. Na raiz do clone:

```powershell
py -3.12 -m venv .venv
py -3.12 -m venv .venv-demo
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r src/gie_multistation/requirements.txt -r src/station_forecasts/requirements.txt
& .\.venv-demo\Scripts\python.exe -m pip install -r demo/requirements-demo-lock.txt -r src/gie_panel/requirements-ui.txt
.\run_multistation_panel.bat
```

O painel fica em `http://127.0.0.1:8504`; API em 8520; High Autonomy V2 original em 8503. Os executáveis Python podem ser definidos por `GIE_CORE_PYTHON` e `GIE_DEMO_PYTHON`. O launcher usa o clone atual, sem cópia de regressão nem dependência do EMPS. Para testes da interface que usam fixtures locais, execute antes ` $env:PYTHONPATH="$PWD\src"; & .\.venv\Scripts\python.exe -B -m gie_panel.ui_fixtures `; esse comando prepara somente arquivos ignorados em `reports/panel/v1/runtime/`.

O comparador em **Residência → Comparar baterias** lê `reports/residential_battery/v1/result.json` e não roda MPC a cada clique. O relatório e as capturas estão na mesma pasta. As trajetórias e checkpoints temporários em `runs/` não são distribuídos; podem ser recriados por `gie_panel.comparison` com ambientes e dependências instalados. Dados, modelos, replays e resumos necessários ao painel estão incluídos. Os relatórios documentam os testes históricos, que não devem ser reexecutados sobre as evidências originais; faça reproduções em cópia separada.

## Preservação do congelamento

O `docs/release/frozen_manifest.json` preexistente registra SHA-256 `c957cd2ba2f792547b6b336183049738eebaa9d4109cf3c1836ae6615f705808` para `demo/high_autonomy_v2/app.py`; o arquivo versionado atualmente tem SHA-256 `897e3d650c1800dd1f7441fa984b703c50b18ce705871b0d4dbbdc59eb3e`. A divergência já existia antes desta publicação. Nenhum dos dois arquivos foi alterado para mascará-la. Os demais controles de preservação constam dos relatórios das fases.

Dados sintéticos e comparações são demonstrações, sem comandos físicos. O comparador não demonstra economia financeira ou compatibilidade definitiva de instalação.
