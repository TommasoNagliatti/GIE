# Contrato lógico para maquete

Fluxo: GIE → decisão → numeric_state → visual_state → backend → controlador futuro.
`visual_state` é somente representação e nunca entrada do MPC.

| Visual | Representação futura | Valor numérico associado |
|---|---|---|
| solar_active | luz solar | solar_kw |
| grid_importing | rede → sistema | grid_import_kw |
| grid_exporting | sistema → rede | grid_export_kw |
| battery_charging | sistema → bateria | battery_charge_kw |
| battery_discharging | bateria → sistema | battery_discharge_kw |
| building_active | prédio aceso | building_kw |
| evse_1_active … evse_4_active | limite de carga autorizado | evse_setpoints_kw[0…3] |
| evse_1_fault … evse_4_fault | indicação de falha | evses.EVSE1…EVSE4.state |

`battery_flow`: charging/discharging/idle/unknown; `grid_flow`: importing/exporting/idle/unknown.
EVSE: charging/idle/fault/disconnected/offline/unknown. Charging descreve setpoint positivo,
não comprova corrente real. Limiar visual 0,00001 kW; números originais não são cortados.

Sempre enviar timestamp, mode, profile, status, execution_allowed e visual_state.valid.
Quando inválido, não reutilizar um comando antigo como se fosse novo nem interpretar null
como zero. A política de equipamento em perda de comunicação segue HARDWARE_INTEGRATION.md.
Os valores completos kW, SOC, previsões kWh, limites, fluxos e eventos continuam na resposta.

ESP32, Arduino, Raspberry Pi ou outro controlador poderão consumir esse contrato por um
adaptador futuro. GPIO/PWM/Modbus/OCPP, transporte, escala da maquete, ACK e readback não
foram implementados. Nenhuma chamada LLM ou API de IA existe nesta camada.
