# Interface pública GIE

API Python em `src/gie_control`. Importação no bundle: `from gie import ...`.

- `GIEEngine(root=None, components=None)`: valida o JSON contra a configuração V2 congelada.
- `initialize_models()`: carrega os modelos necessários; não treina nem consulta clima.
- `run_cycle(decision_time, history, current, mode='NORMAL')`: mesmo runtime V2;
  mantém estado do Load Balancer. O caller fornece SOC real a cada ciclo.

`GIEControl(engine=None, scenes=None, clock=None, demo_runner=None)`:
`get_state`, `set_mode`, `get_mode`, `run_cycle`, `start_presentation`,
`pause_presentation`, `resume_presentation`, `stop_presentation`, `next_scene`,
`previous_scene`, `set_scene`, `set_presentation_interval`, `set_loop`,
`get_presentation_state`, `tick`, `trigger_demo_event`, `reset_demo`.

NORMAL e SIMULATION aceitam telemetria do caller e usam o core verdadeiro.
SIMULATION não cria um dataset ou gerador oculto: o caller identifica sua telemetria simulada.
PRESENTATION reproduz snapshots independentes offline. MANUAL_DEMO aplica somente
os eventos enumerados em `scenarios.EVENTS`, recalculando decisões pelo MPC real.
Eventos manuais são rejeitados em NORMAL/SIMULATION. Troca de modo pausa autoplay.

`get_state` devolve cópia; a edição externa não altera o estado interno.
Não compartilhar uma instância entre instalações, usuários ou threads concorrentes.
Não há servidor HTTP, GPIO, comandos físicos, ACK ou agendamento automático.

A resposta conserva integralmente os campos originais e acrescenta `numeric_state`,
`messages`, `primary_message`, `visual_state`, `maquette_state`, `reason_codes` e proveniência.
Precisão numérica preservada; texto arredonda somente para exibição.
SOC antes/medido e SOC após/calculado são distintos. Setpoints EV são limites.
Falha: `execution_allowed=false`; comandos numéricos ausentes ficam null, visual unknown.
Nunca interpretar falha como comando zero válido.

O JSON de perfil é lido pelas novas camadas; divergência frente à V2 congelada é erro.
Não redefine silenciosamente os limites físicos nem modifica o perfil antigo.
