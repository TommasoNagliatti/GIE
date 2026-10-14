# Energy V3 — MPC multiestação exclusivamente simulado

Nova implementação SciPy/HiGHS, independente do MPC V1/V2. Configuração dinâmica de EVSEs, circuitos, inversores e baterias. Horizonte 48×15 minutos; somente o primeiro passo altera o estado simulado. Não envia comandos físicos, não altera tarifação e não homologa equipamentos GoodWe.

## Reprodução

Na raiz `C:\goodwill_ai\GIE_DATASETS`, PowerShell:

```powershell
$python = 'C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD\src\gie_multistation\.deps"
& $python -B -m unittest gie_energy_v3.test_math gie_energy_v3.test_runtime gie_multistation.test_isolation -v
& $python -B -m gie_energy_v3.simulate --output reports/energy_v3/reproduction
```

Em outra máquina: Python 3.12, venv isolado e dependências de `src/gie_multistation/requirements.txt`; acrescentar matplotlib para gráficos. Definir `PYTHONPATH` para `src`. Não instalar as dependências em ambientes de produção. Os modelos/perfis congelados precisam estar presentes e corresponder aos hashes do registro.

A simulação inicia workers próprios, executa 96 ciclos por estação com inferência real dos modelos locais, reinicia cada worker após 48 ciclos e verifica a restauração. Encerra apenas seus processos. Os resultados contêm CSV dos primeiros passos, planos completos comprimidos, métricas JSON e gráficos. Não roda treinamento.

Para API manual: seguir `../gie_multistation/README.md`, porta 8520 e tokens de escopo por estação. Usar diretório persistente exclusivo, um processo Uvicorn, sem reload. Não executar a demo antiga para regravar evidências históricas da Fase 3. A API inicia sem workers; inicializar explicitamente cada estação.

Regressões originais usam snapshot separado previamente preparado, sem substituir fontes:

```powershell
$env:GIE_DEMO_PYTHON = 'C:\Users\Tommaso\Desktop\Gie\.venv-demo\Scripts\python.exe'
& $python -B -m gie_energy_v3.regression
```

O snapshot local está em `reports/multistation/v1/regression_snapshot`, com `.venv` apontando ao ambiente core para o bridge original. Esse diretório é ignorado e não integra a entrega. Relatórios desta execução ficam exclusivamente em `reports/energy_v3/v1`.

## Contrato de entrada

`Config` explicita rede import/export, lista de inversores (AC e PV DC), baterias (ID, energia nominal, SOC inicial/mínimo/máximo, potências, eficiências, disponibilidade e inversor), EVSEs (ID, potência, mínimo e disponibilidade), circuitos e política. Valores essenciais vêm dos manifestos; ausência/inconsistência bloqueia, sem limites inventados. Configurações alternativas são fixtures de teste, não alterações do cadastro comercial.

`optimize(config, energy, building, pv, demand)` recebe energia individual kWh, 48 cargas obrigatórias kW, matriz 48×inversores de PV disponível e matriz 48×EVSEs de demanda. `allocate` considera conexão, disponibilidade e potência aceita pelo veículo. Mínimo técnico exige admissão ou suspensão; concorrência utiliza max-min e alternância de admissões.

Na API v1, `current.demands[]` ganha `available` (padrão true) e `vehicle_max_kw` opcional. Somente os novos perfis usam essas extensões. O primeiro passo considera a demanda atual, independentemente do recall residencial de 6,778%. Futuro EV é cenário distribuído pelas capacidades; casa mantém envelope conservador da demanda atual. PV futuro usa o dia anterior, sem consultar solar futuro do dataset. Primeiro passo usa fixture atual. Modelos não foram retreinados.

## Saída e continuidade

`state.management`: status, execution_allowed, policy, 48 passos, first_decision, estágios do solver e verificação. Cada passo contém import/export, PV disponível/usado/cortado, carga obrigatória, EV solicitado/atendido, setpoint por EVSE, decisões individuais de bateria e erro de balanço.

`station_extension`: versão 3.0, política, proveniência, decisões individuais e simulation_state. `numeric_state`, `visual_state`, mensagens e campos de compatibilidade permanecem. SOC agregado é apenas exibição. `execution_allowed=true` e `visual_state.valid=true` significam matemática simulada válida; `commands_valid=false`, `physical_dispatch=false`, `hardware_commands_sent=false` continuam obrigatórios.

Checkpoint `energy_state_v3.json` por estação registra energia individual, hash da configuração, último instante e contagem. Escrita temporária + flush/fsync + substituição atômica antes da atualização em memória. Reinício restaura energia, mas limpa decisões/cache e muda generation. Intervalos repetidos ou saltados são recusados; próximo ciclo exige +15 minutos. Resposta perdida exige consultar o estado, nunca repetir cegamente. Checkpoint incompatível/corrompido bloqueia inicialização sem reset automático. Não oferece transação distribuída com clientes nem proteção contra perda do volume.

Problema inviável/falha do solver: execution_allowed=false, diagnóstico e nenhum avanço de SOC. É possível corrigir a entrada e reenviar o mesmo instante ainda não aplicado. Não existe atendimento fictício à edificação.

## Limitações explícitas

- Só simulação; setpoints são limites autorizados e, na simulação, hipótese de consumo obedecido. Não são medição nem ACK de hardware.
- Disponibilidades de bateria/inversor são configuração do problema; nos manifestos atuais são disponíveis. API não ingere falhas físicas desses equipamentos. EVSE admite indisponibilidade atual. Previsão assume disponibilidades constantes; não é garantia de operação futura.
- Envelope compartilhado PV+carga+descarga <= AC é conservador; não representa certificação de topologia DC/firmware.
- Demanda EV do dataset é exógena; energia não atendida não é realimentada em SOC de veículos/sessões. Horizonte sem requisito terminal de SOC pode consumir reserva até o mínimo. Não há tarifa econômica, envelhecimento, rampas ou fases elétricas nesta versão.
- Recall residencial permanece baixo; o envelope conservador não é previsão calibrada nem quantil.
- Binária comum impede também transferência entre baterias; estados, limites e eficiências continuam individuais. Pode ser conservador em instalações que permitam transferência deliberada.
- Solver exige ótimo em todos os estágios; timeout bloqueia, sem aceitar solução parcial. Resultados de 24h não constituem garantia para todo cenário anual.

Formulação, comparação, segurança, preservação e evidências: `../../reports/energy_v3/v1/RELATORIO_FINAL.md`.
