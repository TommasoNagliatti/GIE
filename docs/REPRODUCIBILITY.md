# Reproducibility and artifact policy

Run commands from the repository root. Python 3.12 was used locally. The trained models and three official synthetic CSVs are included; normal demo use does not require training or EnergyPlus.

## Environments
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
py -3.12 -m venv .venv-demo
.\.venv-demo\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe -B tools/run_tests.py
.\.venv-demo\Scripts\python.exe -B tools/run_tests.py --demo
.\run_demo.bat
```
If the Windows Python launcher is unavailable, use a Python 3.12 executable in place of `py -3.12`. Installation is explicit; launchers never install packages.

SciPy was already installed and used by the MPC; its installed version is now recorded in requirements. Core and Streamlit environments remain separate. The portable runner verifies a release SHA-256 manifest covering frozen code, models, data, tests and demos. Three older tests check historical local disk snapshots (including old ignore/dependency files); they are explicitly skipped in the portable runner because that snapshot contains private migration archives. Their purpose is covered by the release manifest, not silently discarded.

## Demo modes
- **Replay:** eight saved scenarios; offline, without model inference. Scenarios are independent, not a continuous SOC trajectory.
- **Live Demo:** existing trained engines and runtime, current weather/cache/fallback; historical inputs and current measurements are demonstrative, not physical telemetry. Requires both environments. No real equipment is commanded.
- **Simulation Mode:** accelerated 15-minute cycles, persisted SOC, simulated telemetry and disturbances; existing runtime and components. No internet required for the declared synthetic weather fixture.
- **High Autonomy comparison:** `run_high_autonomy_v2.bat` opens saved 96-cycle V1/V2 playback. Switching the profile does not rerun or reimplement the optimizer.

## Included versus local-only
Included: source, trained V1/V2 models and selectors, official datasets, compact metric tables, saved cycles required by offline demos, selected screenshots and graphs. Model metadata retains original provenance strings byte-for-byte; these old paths are not runtime requirements. Some legacy engine names also remain in frozen metadata. The preserved OSM also contains its original weather-file reference: relink it to your downloaded EPW in OpenStudio. Git attributes disable newline conversion so frozen hashes survive a checkout.

Ignored but not deleted: environments, weather caches, live sessions, prediction matrices, EnergyPlus intermediates, migration backups and historical whole-disk manifests. No file over 25 MiB is intended for this release. Weather source packages are downloaded separately and retain their own terms.

Training entry points (for a **separate experiment copy**, never to overwrite frozen references):
- Building V1: `src/motor_consumo/v1/train.py`; residual/hybrid V2: `src/motor_consumo/train.py`.
- EV V1: `src/motor_carregadores/train.py`; V2 selector/Q90: `src/motor_carregadores_v2/train.py`.
- Evaluation: corresponding `evaluate.py` modules. They generate larger prediction matrices omitted from publication.
- EV synthetic sessions: `simulacao/carregadores/gerar_carregadores.py` (use `--help` for its output arguments).
- Building: `simulacao/energyplus/modelo/predio_sp.idf`, its OSM and scripts in `simulacao/energyplus/scripts/`. Original engine: EnergyPlus 25.2, OpenStudio SDK 3.11.0. Configure the executable for your installation; do not assume the original Windows installation path.
- Weather: download [São Paulo–Congonhas TMYx 2011–2025](https://climate.onebuilding.org/WMO_Region_3_South_America/BRA_Brazil/SP_Sao_Paulo/BRA_SP_Sao.Paulo-Congonhas.AP.837800_TMYx.2011-2025.zip) and place its EPW under `simulacao/energyplus/clima/`. This is a typical meteorological year, not measured 2026 weather.
- High Autonomy comparison: `demo/high_autonomy_v2/compare.py` consumes saved V1 cycles and produces V2 results. Existing results are already included; rerunning is unnecessary for viewing.

January–April training, May selection/validation; June became a diagnostic after iterative development. July was evaluated with frozen models. EV July is a synthetic extension: arrival factor 1.03 and peak shift −0.03 hour inherited from June and preregistered before generation. No July calibration was performed.

## Português
Os modelos e CSVs oficiais acompanham o repositório. Os comandos acima criam dois ambientes separados e executam os testes sem retreinar. Replay e a comparação V1/V2 usam resultados salvos. Live Demo utiliza clima atual e modelos reais com telemetria demonstrativa. Simulation Mode usa telemetria e clima sintéticos.

Arquivos grandes/intermediários e históricos de migração continuam preservados localmente, mas não são publicados. Caminhos antigos em metadados congelados registram proveniência e não são necessários para execução. Para gerar novos resultados, use uma cópia de experimento e os pontos de entrada listados; preserve os modelos e resultados de referência.
