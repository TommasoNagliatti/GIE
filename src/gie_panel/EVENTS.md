# Contrato local GIE → Backend EMPS — versão 1.0

Não há envio de e-mail, SMS, push ou integração financeira nesta fase. O Backend NestJS continuará responsável por autenticação humana, permissão da estação, destinatários e entrega.

## Consulta autenticada

Bearer server-to-server com escopo explícito. IDs fora do escopo retornam 403; sem credencial, 401. A UI não recebe a credencial no cliente do navegador.

- `GET /panel/{station_id}/alerts?severity=critical&status=OPEN&equipment_id=EVSE3`: filtros opcionais.
- `POST /panel/{station_id}/alerts/{alert_id}/ack`: idempotente para o mesmo alerta; não resolve.
- `GET /panel/{station_id}/events?after=0`: até 500 eventos, ordenados por cursor; próxima página usa o último cursor recebido. Cursor global pode ter lacunas porque a consulta é filtrada por estação.

Envelope: `schema_version`, `event_id`, `alert_id`, `station_id`, `emitted_at`, `transition`, `alert`, `physical_dispatch=false`, `hardware_commands_sent=false`.

`event_id = alert_id:revision` identifica cada evento; consumidores devem impor unicidade desse ID. `alert_id` permanece estável em reconhecimento, recuperação e reabertura. Transições: CREATED, UPDATED, ACKNOWLEDGED, RESOLVED, REOPENED. UPDATED é observação contínua, não uma nova ocorrência/notificação. `occurrence_count` só cresce na reabertura após resolução.

O alerta inclui geração do worker, instante energético `timestamp`, detecção UTC `detected_at`, `first_seen`, `last_seen`, equipamento opcional, código, severidade, título, descrição, reason_codes, numeric_context, provenance, source_ref, status, acknowledged_at e resolved_at. `emitted_at` é horário real do evento; tempos energéticos simulados podem retroceder ao iniciar outro cenário. O Backend não deve ordenar consumo do feed por timestamp energético: use cursor/revision.

Deduplicação: estação + código + equipamento. Chave de observação distingue run, geração e revisão/cena; polling do mesmo resultado não gera eventos. As origens identificam o runtime e o evento observado, sem inferir causa interna de solver.

## Recuperação determinística

- Demanda EV não atendida: entra acima de 0,10 kW; permanece acima de 0,05 kW.
- Importação: entra acima de 95% do limite; permanece acima de 90%.
- SOC: entra até mínimo +2 pontos percentuais; permanece até mínimo +4 pontos.
- Resolução exige duas observações válidas distintas do domínio correspondente. Falta de telemetria não prova recuperação energética. Disponibilidade de bateria/inversor só é avaliada para equipamento cadastrado com observação explícita; nenhum alerta de bateria é inventado para casa sem bateria.
- Reconhecimento mantém a condição ativa. Reinício da API/worker preserva alertas críticos, histórico e IDs. Uma nova geração é um evento informativo separado.
- Os detectores reutilizam reason_codes/mensagens originais. Capacidade insuficiente significa carga obrigatória observada maior que um limite superior explícito de fornecimento; não explica a causa interna do solver.

## Outbox EMPS existente

Inspecionado `EMPS_GITHUB/site/emps-site-main/backend/src/notification.gateway.ts`: o transporte de desenvolvimento já persiste JSONs em `reports/notification-outbox` (ou diretório configurado), com tipos station-review/station-invite e retorno LOCAL_OUTBOX/sentEmail=false. Esse mecanismo não foi alterado nem duplicado.

Na Fase 6, um adaptador autorizado do Backend poderá consultar este feed, persistir o cursor somente após consumo idempotente e mapear CREATED/REOPENED/RESOLVED conforme política de notificação. UPDATED não implica redistribuição; ACKNOWLEDGED registra ação humana. O Backend deve guardar quem reconheceu e verificar permissão da estação. A autenticação local atual é de serviço, não de usuário; não atribui proprietário ou destinatário. Persistência SQLite aqui é apenas o ledger de testes, não uma nova outbox comercial.

Exemplos reais de eventos simulados em `reports/panel/v1/event_examples.json`; os IDs são de teste e não devem ser reutilizados em produção.
