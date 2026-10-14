# GIE multiestação local — Fases 3 e 4

Extensão Fase 5 disponível em `../gie_provisioning/README.md`: cadastro dinâmico validado, BASELINE sem histórico, rotas v2 e capability de provisionamento. Rotas/perfis anteriores permanecem. Credenciais podem pré-autorizar IDs seguros ainda não cadastrados; criação exige também `GIE_PROVISIONING_TOKENS`. Não há wildcard nem ativação automática de modelos/hardware.

Um único FastAPI, um processo `spawn` por estação. Sem hardware, serviço comercial, faturamento ou alteração do Backend. Dados e entradas são sempre **SIMULATED**, inclusive no modo NORMAL.

A Fase 4 habilita Energy V3 + allocator novos para posto/casa; comercial permanece congelado. Consulte `../gie_energy_v3/README.md` para simulações, contratos e testes atuais. Evidências históricas da Fase 3 não devem ser sobrescritas.

## Executar no computador atual

PowerShell, na raiz `C:\goodwill_ai\GIE_DATASETS`:

```powershell
$python = 'C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe'
$env:PYTHONPATH = "$PWD\src;$PWD\src\gie_multistation\.deps"
& $python -B -m gie_energy_v3.simulate --output reports/energy_v3/reproduction
& $python -B -m unittest gie_multistation.test_isolation -v
```

A ferramenta histórica `demo` inicia uma API HTTP de loopback em porta livre, inicializa as três estações simultaneamente, executa ciclos e controles comerciais e encerra seus próprios processos. Credenciais efêmeras ficam apenas em memória. Evidência: `reports/multistation/v1/http_demo.json`. Isso não inicia nem modifica o EMPS de produção.

Para deixar a API disponível para teste manual em **127.0.0.1:8520**:

```powershell
$token = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$scopes = @{}
$scopes[$token] = @('Commercial_HighAutonomy_V2','DEMO_POSTO_24H_001','DEMO_CASA_001')
$env:GIE_MULTISTATION_TOKENS = $scopes | ConvertTo-Json -Compress
$env:GIE_MULTISTATION_DATA_DIR = "$PWD\reports\multistation\v1\runtime"
& $python -B -m gie_multistation --port 8520
```

Mantenha esse processo aberto; Ctrl+C encerra os workers. O token deve ser transmitido ao cliente de teste por meio privado, nunca salvo no Git. O serviço inicia sem workers: chamar `/initialize` para cada estação. Não usar múltiplos workers Uvicorn ou reload sobre o mesmo diretório. Há trava exclusiva de proprietário.

Em outra máquina, criar venv Python 3.12 isolado e instalar `src/gie_multistation/requirements.txt`. Nesse caso, definir `PYTHONPATH` somente como a pasta `src`; `.deps` é uma instalação local isolada usada nesta validação, não deve ser versionada. Nenhuma dependência global foi alterada. Para os testes de UI antigos, seguir os dois ambientes da documentação original.

## Componentes

- `stations.json` / `registry.py`: registro local confiável, identidade fixa, perfil físico e hashes. Não recebe paths do cliente.
- `engines.py`: modelos originais no comercial; Forecaster da Fase 2 por estação nos novos perfis. Sem reescrever os motores.
- `manager.py`: processo, GIEControl, mailbox serializada, histórico, cache, alocação, mensagens e arquivos próprios por estação; timeout e recuperação explícita.
- `api.py`: autenticação de serviço, escopo por estação, contratos estritos, rotas v1.
- `test_isolation.py`: processos reais, inferência real e cenários de falha.
- `demo.py`: demonstração HTTP real de três estações.
- `regression.py`: executa regressões em snapshot separado. `GIE_DEMO_PYTHON` escolhe o Python da UI; o bridge da demo ainda exige `.venv/Scripts/python.exe` dentro do snapshot.

Detalhes em `API.md`, `COMPATIBILIDADE.md` e `reports/multistation/v1/RELATORIO_FINAL.md`.
