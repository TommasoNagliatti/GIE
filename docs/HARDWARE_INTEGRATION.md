# Integração futura com hardware
Especificação de interfaces; nenhuma integração física implementada nesta versão.

## Contrato comum
Cada leitura contém site_id, equipment_id, timestamp da medição, received_at, unidade, qualidade (good/stale/bad/unknown), origem e número de sequência. Freshness máxima, tolerância de relógio, timeout, tentativas e tolerância de confirmação são configurações por equipamento. Leituras inválidas ou antigas não equivalem a zero.
Cada comando contém command_id idempotente, cycle_id, timestamp, valid_until, equipamento, valor e unidade. Registrar solicitação, ACK, rejeição, aplicação e leitura posterior separadamente. ACK de aceitação não comprova aplicação. Confirmar setpoint por leitura posterior dentro da tolerância e prazo configurados; registrar divergência.

## InverterAdapter
read_state(): solar AC medida, bateria carga/descarga, SOC, limites disponíveis, alarmes, disponibilidade e qualidade. Convenções: carga e descarga positivas em campos separados.
apply_battery_setpoint(): comando assinado com convenção explícita ou campos mutuamente exclusivos, respeitando limites locais. read_command_status() e readback confirmam aplicação. Configuração identifica suporte a exportação e medição de cada equipamento.

## MeterAdapter
read_measurements(): importação e exportação separadas, potência do prédio e EV quando submedidas, energia acumulada, tensão/corrente/fases quando disponíveis. Não subtrair medidores com timestamps incompatíveis. Sem comandos de potência.

## EVSEAdapter
read_state(): conexão, estado/falha, início da sessão, potência real, capacidade EVSE e veículo quando conhecida, mínimo de carga configurado e qualidade.
set_power_limit(): limite por EVSE, command_id e validade; stop/suspend quando suportado. Confirmar limite aplicado e consumo real separadamente: veículo pode consumir abaixo do limite.
Conversão de kW para corrente depende de tensão, fases, fator de potência e suporte do equipamento; não assumir valores universais.

## Perda de comunicação
Expirar comandos antigos; não aumentar potência com telemetria obsoleta. Registrar componente degradado e bloquear novas decisões quando faltarem medições obrigatórias. Adaptador deve aplicar política local segura previamente validada (por exemplo suspender EV e cessar comandos de bateria quando tecnicamente suportado), sem presumir que um comando perdido foi executado.
Proteções físicas locais, BMS e intertravamentos permanecem obrigatórios. Software remoto não consegue garantir limite da rede durante perda de comunicação. Retomar somente após telemetria válida e reconciliação de comandos/setpoints.
Timeouts e fallback devem ser validados no comissionamento, não inventados pelo core.

## Separação
Modbus, APIs de fabricante e OCPP são possíveis implementações futuras atrás das interfaces. Core recebe unidades e contratos normalizados e não depende desses protocolos. Credenciais ficam fora dos registros de decisão. Nenhum driver, cobrança ou controle real é incluído nesta entrega.
