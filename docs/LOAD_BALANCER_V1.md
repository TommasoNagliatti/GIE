# Load Balancer V1

Módulo determinístico abaixo do Motor 3. Recebe seu `ev_block_limit_kw` (0–88 kW) e produz quatro setpoints de 0–22 kW. Não modifica ou chama os Motores 1, 2 ou 3; não usa IA, LLM, rede nem SOC do veículo. O código de produção usa somente a biblioteca padrão do Python. O gráfico usa o Matplotlib já instalado no projeto.

## Distribuição

Para cada EVSE apto, a capacidade é o menor valor entre 22 kW, limite reportado pelo EVSE e limite aceito pelo veículo (se conhecido). EVSE desconectado, em falha, offline ou suspenso recebe zero.

Sem mínimo configurado, o algoritmo calcula `p_i = min(capacidade_i, nível_comum)`. Aumenta o nível comum até consumir o orçamento ou saturar todos os dispositivos. A busca mantém sempre o lado viável do limite, sem arredondar os comandos para cima. Capacidades menores liberam sobra automaticamente: 54 kW para capacidades [22, 11, 22, 0] resulta em [21,5, 11, 21,5, 0].

`requested_kw` representa a capacidade disponível para alocação, não uma medição da potência realmente consumida. Sem limite do veículo conhecido, utiliza-se o limite do EVSE, limitado a 22 kW. Quando o veículo reduz sua aceitação, o chamador deve atualizar essa capacidade no próximo ciclo. A potência efetivamente consumida pode ser menor que o setpoint; este módulo não inventa essa telemetria.

`Config(minimum_kw={'EVSE1': ...})` configura um mínimo por EVSE em kW. O padrão é zero (nenhum mínimo físico presumido). Se o mínimo for positivo, cada comando será zero ou maior/igual ao mínimo, sem ultrapassar a aceitação reportada. São examinados no máximo 16 subconjuntos de EVSEs, escolhendo o vetor ordenado de potências lexicograficamente máximo: primeiro maximiza o menor atendimento, depois o segundo menor, etc. A chegada mais antiga desempata apenas vetores equivalentes; empates exatos restantes usam rodízio entre ciclos, sem prioridade fixa por ID. Capacidade menor que o mínimo implica setpoint zero.

Com mínimos positivos, a restrição liga/desliga pode exigir pausas e deixar sobra que não permite admitir outro dispositivo. O rodízio em empates exatos pode alternar os dispositivos; tempos mínimos de permanência ligados/desligados dependerão do hardware e não foram inventados nesta V1. Sem mínimos positivos, sessões equivalentes recebem a mesma potência e entradas constantes produzem saídas idênticas. Não há rampa ou suavização que retarde reduções de segurança.

## Uso em produção

Execute com `src` no caminho de importação (por exemplo `$env:PYTHONPATH="src"` no PowerShell).

```python
from load_balancer import EVSEState, run_balancer

evses = [
    EVSEState('EVSE1', True, connected_since='2026-08-01T08:00:00'),
    EVSEState('EVSE2', True, vehicle_max_kw=11, connected_since='2026-08-01T08:15:00'),
    EVSEState('EVSE3', True, connected_since='2026-08-01T08:30:00'),
    EVSEState('EVSE4'),
]
resultado, estado = run_balancer(54, evses, '2026-08-01T09:00:00')
# No próximo ciclo, passar previous=estado e o novo limite/telemetria.
```

O retorno contém timestamp, limite, totais solicitado/alocado, `evse_1_kw` até `evse_4_kw`, detalhes de EVSE1–EVSE4 e eventos. Conexões, desconexões e falhas são eventos de transição; limitação e bloco totalmente alocado são informações do ciclo. O primeiro snapshot conectado/falho gera o respectivo evento. Bloco zero não gera evento de bloco totalmente alocado.

São exigidos exatamente quatro IDs únicos e estados válidos. Blocos negativos, maiores que 88, não finitos, capacidades inválidas e início de sessão futuro são rejeitados. Use timestamps consistentemente locais ou consistentemente com fuso. Dados inválidos geram exceção sem devolver novos setpoints; o futuro adaptador de hardware deverá tratar essa exceção e o timeout de comunicação. Este módulo não envia comandos OCPP nem controla equipamento físico.

## Verificação e simulação

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/load_balancer -v
.\.venv\Scripts\python.exe -B src/load_balancer/demo.py
```

A simulação contém 48 ciclos de 15 minutos, conexões/desconexões, um veículo limitado a 11 kW, falha do EVSE3, bloco zero e mudanças de limite. Os limites são fictícios para exercitar o módulo, sem alterar o Motor 3. Artefatos em `outputs/load_balancer/v1`: CSV, JSON completo, eventos, exemplo, gráfico, resumo, testes e manifesto de preservação dos arquivos preexistentes. A suíte inclui 2.000 casos aleatórios reproduzíveis com verificação de capacidade, conservação do orçamento, utilização e max-min fairness.
