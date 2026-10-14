# API v1 e integração futura

Fase 5: rotas de cadastro/configuração/ciclo dinâmico em `/v2/stations`, documentadas em `../gie_provisioning/README.md`. Rotas v1 existentes permanecem; novas estações utilizam lifecycle v1 e current com proveniência v2. Escopos explícitos podem conter IDs futuros seguros; só tokens com capability adicional podem cadastrá-los. Não há wildcard nem aceitação automática do gieContract 2.0 do Backend.

Todas as rotas exigem `Authorization: Bearer <token>`. Configuração em memória via `GIE_MULTISTATION_TOKENS`: objeto JSON token -> lista explícita de station_ids autorizados, sem wildcard. Tokens com pelo menos 24 caracteres. A identidade vem da rota + escopo do token; todos os corpos proíbem campos extras, incluindo station_id. Tokens e cabeçalhos não são registrados. Esta API não cria usuário, sessão de recarga nem cobrança.

| Método | Rota | Corpo / comportamento |
|---|---|---|
| GET | `/v1/health` | Serviço e processos das estações autorizadas |
| GET | `/v1/stations` | Somente registros autorizados |
| GET | `/v1/stations/{station_id}/health` | running/stopped/failed, PID e geração |
| POST | `/v1/stations/{station_id}/initialize` | `{}`; idempotente se já iniciado |
| GET | `/v1/stations/{station_id}/state` | Estado do worker; avança Presentation por tick como no controle original |
| POST | `/v1/stations/{station_id}/cycle` | `{}` para fixture inicial; depois issue_time crescente com offset |
| POST | `/v1/stations/{station_id}/mode` | `{"mode":"NORMAL"}` ou SIMULATION/PRESENTATION/MANUAL_DEMO conforme capacidade |
| POST | `/v1/stations/{station_id}/presentation` | action start/pause/resume/stop/reset/next/previous/scene/interval/loop |
| POST | `/v1/stations/{station_id}/manual-demo/event` | `{"event":"EV_PEAK"}`; RESET e eventos comerciais originais |
| POST | `/v1/stations/{station_id}/stop` | `{}`; idempotente |
| POST | `/v1/stations/{station_id}/restart` | `{}`; nova geração/cache vazio; Energy V3 restaura somente energia simulada, sem replay |

Presentation scene exige scene_id (01 a 16), interval exige seconds (5/10/15), loop exige enabled booleano. Presentation e Manual Demo são exclusivamente comerciais: perfis novos retornam 422 e não exibem as cenas comerciais com outra identidade.

Ciclo residencial demonstrativo:

```json
{
  "issue_time": "2025-10-01T12:15:00-03:00",
  "current": {
    "building_kw": 0.2,
    "solar_kw": 0.0,
    "demands": [{"evse_id":"EVSE_01","requested_kw":7.0,"connected":true}]
  }
}
```

`current` é opcional, sempre simulado nesta versão. Exige exatamente os EVSEs cadastrados: casa EVSE_01, posto EVSE_01/EVSE_02, comercial EVSE1..EVSE4. Limites por dispositivo, desconectado com potência positiva, duplicatas, NaN, infinito e potência solar incompatível são recusados. Não há recepção de telemetria física ou histórico externo nesta fase. Não usar este endpoint para declarar medições MEASURED.

Origens padrão: comercial 2026-06-15T12:00:00-03:00; demais 2025-10-01T12:00:00-03:00. Datas pertencem às fixtures, não ao relógio real. Repetir ou retroceder issue_time é recusado; avançar 15 minutos. Histórico das previsões inclui somente intervalos anteriores à emissão. O estado atual simulado é separado desse histórico.

Respostas mantêm envelope de estação e state do GIE; comercial conserva contratos originais. Na Fase 4, posto/casa usam Energy V3: management contém 48 passos, decisões individuais, verificação e política. Quando viável, execution_allowed=true e visual_state.valid=true; commands_valid=false, physical_dispatch=false e hardware_commands_sent=false permanecem. Setpoints são limites simulados, não medições/aplicação em equipamento. station_extension inclui energy_version, simulation_state e battery_decisions. SOC agregado é somente exibição. forecast solar_previsto_kw legado pode permanecer null; fonte solar efetivamente usada está explicitada na extensão e nos planos.

Extensões opcionais de current.demands para os novos perfis: available booleano e vehicle_max_kw não negativo. O comercial não usa esses campos. /cycle vazio avança automaticamente o próximo intervalo de 15min após o inicial. Replay e gaps são recusados. Problema matemático inviável retorna diagnóstico sem avançar SOC; entrada corrigida pode repetir o instante não aplicado.

Checkpoint energy_state_v3.json por estação contém energias individuais, configuração e último ciclo. Reinício restaura somente esse estado simulado, mantém generation nova e não reapresenta comandos. Checkpoint incompatível bloqueia sem reset. Após resposta perdida, consultar simulation_state antes de decidir o próximo instante. Contrato detalhado em ../gie_energy_v3/README.md.

401: token ausente/inválido. 403: estação fora do escopo (também evita enumerar desconhecidas). 422: corpo, tempo, capacidade ou operação incompatível. 503: worker parado/perdido/timeout. Erro não promove o último comando a válido. Reiniciar explicitamente; não repetir automaticamente ciclos com efeito presumido. `initialize` e lifecycle são idempotentes onde documentado; não há garantia exatamente-uma-vez após queda.

## Backend futuro

1. Manter autorização de usuário, associação de estação, sessão, reserva e faturamento no Backend. Resolver sua identidade para um registro GIE aprovado; não aceitar caminhos ou perfis arbitrários do usuário.
2. Usar tokens de serviço de escopo mínimo; substituir o singleton/cache global do cliente por caches e polling separados por station_id e generation. Este trabalho não altera o Backend.
3. Tratar mudança de generation como reinício: descartar decisões antigas e reenviar contexto somente após validar capacidades e proveniência. snapshots locais são auditoria, não comando restaurado.
4. `execution_allowed` comercial descreve a decisão matemática demonstrativa original; **physical_dispatch=false e hardware_commands_sent=false em todas as estações**. Nenhum cliente deve acionar equipamento a partir desta demo.
5. Projetar depois ingestão autenticada de telemetria, freshness, mapeamento de equipamentos, ACK/readback, transportes físicos, TLS, quotas e supervisão operacional. Não há gateway físico nesta API.
6. Para o container futuro em VPS: um processo API, filhos spawn, volume gravável separado por estação, modelos/datasets somente leitura, limite de CPU/RAM por implantação e encerramento gracioso. Bind atual é loopback. Exposição externa, proxy, Docker e deploy precisam de etapa própria.
