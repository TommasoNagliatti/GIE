# Fase 5 — cadastro dinâmico e BASELINE

Extensão local exclusivamente SIMULATED. Reutiliza Energy V3 sem alterar sua matemática ou os previsores da Fase 2. Comercial, Presentation, Manual Demo e as 16 cenas continuam no motor original. Não modifica Backend, Site, App, banco ou Docker.

## Iniciar

PowerShell em `C:\goodwill_ai\GIE_DATASETS`:

```powershell
$python = 'C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD\src\gie_multistation\.deps"
$token = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$scope = @{}
$scope[$token] = @('Commercial_HighAutonomy_V2','DEMO_POSTO_24H_001','DEMO_CASA_001','NEW_NO_HISTORY')
$env:GIE_MULTISTATION_TOKENS = $scope | ConvertTo-Json -Compress
$env:GIE_PROVISIONING_TOKENS = ConvertTo-Json -InputObject @($token) -Compress
$env:GIE_MULTISTATION_DATA_DIR = "$PWD\reports\provisioning\v1\runtime"
& $python -B -m gie_multistation --port 8520
```

Um processo API, sem reload/workers adicionais sobre o mesmo diretório. Servidor somente em loopback. Cada estação inicia seu próprio processo por `/initialize`; cadastrar não inicia automaticamente. Use o token de forma privada, nunca em arquivos versionados. O token precisa de duas autorizações para criar: escopo explícito do station_id e capability de provisionamento. IDs ainda não cadastrados podem ser pré-autorizados pelo operador, sem wildcard. Não existe endpoint para autoampliar permissões. Alterar a configuração de credenciais exige reiniciar a API; criar/parar/recuperar uma estação previamente autorizada não reinicia as demais.

Em outro computador: Python 3.12 e dependências de `../gie_multistation/requirements.txt`, mais matplotlib para gráficos. `PYTHONPATH=src`; `.deps` é particular deste ambiente e não deve ser versionado. Não é necessário CSV/modelo de outra estação para inicializar a nova estação; o serviço original ainda carrega/verifica seu registro legado ao iniciar.

## Rotas novas

| Rota | Contrato |
|---|---|
| POST `/v2/stations` | `Provision`: criação técnica imutável; repetição idêntica retorna o mesmo cadastro; alteração retorna 409 |
| GET `/v2/stations/{id}/configuration` | Configuração aprovada local, somente para escopo autorizado |
| POST `/v2/stations/{id}/cycle` | `DynamicCycle`: instante explícito e current opcional, exclusivo das estações dinâmicas |
| POST `/v2/stations/{id}/model-transition` | Valida contrato de transição; retorna 409 enquanto adaptador confiável de modelos não existir; não ativa nem simula uma ativação |

As rotas v1 de listagem, health, initialize, state, stop, restart e mode atendem também as novas estações. Seus IDs/configurações são persistidos e recuperados no reinício. NORMAL e SIMULATION disponíveis; Presentation/Manual Demo permanecem comerciais. A rota v1 de ciclo mantém contrato legado; para enviar current com proveniência à estação nova, usar v2.

O esquema completo e validadores estão em `contracts.py`. Aceita ID seguro até 64 caracteres (inclusive ID numérico como string), timezone IANA, limites de rede, até 64 EVSEs, 16 baterias, 32 inversores/ativos solares e 64 circuitos. Esses limites protegem o serviço local; não afirmam escalabilidade para produção. Arrays de solar, bateria ou EVSE podem ser vazios. Valores são kW/kWh; SOC/eficiência são frações 0–1. IDs de circuitos, EVSEs, baterias, inversores e solar devem ser únicos em suas listas; referências cruzadas precisam existir.

Os parâmetros elétricos essenciais são obrigatórios. SOC inicial é condição SIMULATED declarada da bateria, nunca leitura física. Solar referencia inversor; nenhum ativo solar equivale a ausência de fonte instalada, não irradiância observada. `baseline_building_kw` é uma hipótese técnica opcional de demanda futura, não consumo medido. Se omitida e não houver current confiável, previsão do prédio fica null. Não se converte limite de rede em medição de consumo.

Não há caminho/URL/arquivo fornecido pelo cliente. O servidor guarda `configurations/{id}.json` validado com checksum, e `{id}/` com modelos (metadados BASELINE), histórico, cache, journal, snapshot e checkpoint. Estado operacional/histórico/cache em memória são privados do worker; journal/checkpoint persistem. Modelos personalizados não são copiados de outro perfil. Configuração não pode ser editada pela API nesta versão. Conflito com diretório preexistente exige inspeção, sem remoção automática. Checksum detecta corrupção acidental, não substitui controle de acesso ao disco.

## Sem histórico: decisão segura

`BASELINE` é o estado do treinamento na criação. Não exige 2.689 registros nem carrega LightGBM para essa estação. Previsão inicial tem 48×15min, `origin=ESTIMATE`, `is_measurement=false` e método `technical_envelope_v1`:

- Prédio: hipótese técnica configurada; com current confiável, máximo entre hipótese e potência atual. Não é garantia probabilística de pico futuro.
- EV futuro: capacidade disponível instalada, cenário conservador de concorrência; não afirma ocupação ou chegada real. Demanda atual decide o primeiro passo, limitada por veículo, disponibilidade, circuito e rede.
- Solar futuro: zero garantido por prudência; só o primeiro passo pode usar solar atual explícito. Não inventa previsão meteorológica.

`current` deve incluir station_id, observed_at, available_at, origin=SIMULATED, quality=TRUSTED, prédio, solar e todos os EVSEs da estação. TRUSTED é declaração do emissor autorizado sobre a fixture de simulação, não autenticação de medidor. Na ausência, fonte não confiável ou atraso acima de cinco minutos em relação ao instante simulado do ciclo, retorna `operational_state=DEGRADED`, execução falsa, números atuais/despacho desconhecidos como null e nenhuma evolução de SOC. Não compara data sintética com relógio de parede.

Instantes exigem offset e alinhamento de 15 minutos; timezone da estação é preservado. `available_at` não pode anteceder observed_at nem exceder o instante de decisão. Amostra de outra estação ou incompleta é rejeitada. Origem MEASURED é recusada nesta API; não há entrada de telemetria física.

Disponibilidades atuais opcionais de bateria/inversor/rede reduzem a configuração aprovada, nunca ampliam limites. Estado de disponibilidade é mantido constante no horizonte como hipótese. Bateria indisponível preserva energia; inversor indisponível bloqueia suas cargas/descargas/PV. SOC é persistente e individual; não é reestimado a partir de previsão. Carga obrigatória inviável bloqueia o ciclo em vez de inventar atendimento. Envelope conservador pode restringir a operação mesmo com primeiro passo aparentemente possível, se o horizonte for inviável.

Somente o primeiro passo verificado é aplicado ao estado simulado; checkpoint é atômico. Replay e gaps são rejeitados depois do primeiro ciclo aplicado. Falha/degradação não consome o instante: entrada corrigida pode repetir o intervalo ainda não aplicado. Após perda da resposta, consultar simulation_state; não reenviar cegamente. Reinício restaura SOC, limpa decisões/cache operacional e gera generation nova. Não há transação distribuída com o futuro Backend.

## Modelos e versões

`ModelState` v1 prepara BASELINE, CANDIDATE (candidate_version obrigatória), PERSONALIZED (active_version obrigatória) e DEGRADED. Treinamento e condição operacional são separados: falta de current não transforma BASELINE em modelo personalizado nem apaga seu estado.

`ModelVersion` prepara REGISTER_CANDIDATE, ACTIVATE e ROLLBACK com station_id, version, expected_revision, hash do artefato e hash da validação aprovado para ACTIVATE. Futuro consumidor deverá conferir os arquivos próprios da estação, causalidade, métricas, schema, aprovação e revisão antes de trocar um ponteiro ativo; rollback deve referenciar versão previamente aprovada da mesma estação. Não aceitar paths arbitrários, pickle/código enviado pelo cliente, modelos emprestados ou treinamento automático.

**Nesta fase não existe ativação de modelo personalizado.** `activation_supported=false`; endpoint de transição recusa a mudança sem alterar o BASELINE. Estados/contratos estão preparados e testados, mas validação/carregamento de novos artefatos aprovados é etapa posterior. Isso impede declarar PERSONALIZED apenas porque o cliente enviou uma string.

## Validar e reproduzir

```powershell
& $python -B -m unittest gie_provisioning.test_provisioning -v
& $python -B -m unittest gie_energy_v3.test_math gie_energy_v3.test_runtime gie_multistation.test_isolation -v
& $python -B -m gie_provisioning.seasonal
& $python -B -m gie_provisioning.baseline_week
$env:GIE_DEMO_PYTHON = 'C:\Users\Tommaso\Desktop\Gie\.venv-demo\Scripts\python.exe'
& $python -B -m gie_provisioning.regression
```

As simulações escrevem evidências somente em `reports/provisioning/v1`; para preservar uma execução anterior, copiar essa pasta antes de reproduzir. Nunca reescrevem datasets, modelos ou relatórios anteriores. A regressão original usa o snapshot separado já preparado na Fase 3 e salva logs novos nesta fase.

Exemplos Python/JSON de criação e current: `examples.py` e `reports/provisioning/v1/example_*.json`. A prova das quatro estações é `four_stations.json`, via FastAPI TestClient ASGI e quatro processos reais, não servidor público nem teste de rede externa.

## Fronteira EMPS

O `gieContract` 2.0 do Backend é PREPARED_NOT_ACTIVATED e não é automaticamente aceito como `Provision` 1.0. O adaptador futuro precisa selecionar snapshot técnico aprovado, mapear `grid.powerLimitKw` para importação e exigir exportação explicitamente; mapear chargers/IDs/potências, batteries/SOC inicial simulado/eficiências, solarAssets/inversores/circuitos e INACTIVE→available=false. Ausência de parâmetro essencial deve impedir criação; sem defaults inventados. Preservar IDs como strings para evitar perda de BIGINT.

Backend continua responsável por usuário, aprovação técnica, sessões, START, reserva, pagamento, disponibilidade operacional e autorização. Este serviço não abre sessão nem cobra. A integração futura precisa de credenciais por estação, polling/cache por station_id e generation, idempotência de provisionamento, observabilidade, freshness verificada, schema de telemetria, política de atualização de cadastro e revisão de segurança.

Antes de produção/hardware: TLS, gestão de segredos, quotas de processos/CPU/disco, backup/recuperação do volume, promoção real dos modelos, supervisão física, interfaces homologadas, ACK/readback e testes de bancada. Não há OCPP/Modbus/GoodWe neste módulo. Todas as respostas mantêm `physical_dispatch=false` e `hardware_commands_sent=false`.
