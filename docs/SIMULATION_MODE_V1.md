# Simulation Mode V1
Ferramenta removível em demo/simulation; não altera core, observabilidade, modelos ou datasets oficiais.
Iniciar: run_demo.bat → Simulation Mode. Escolha início em junho (histórico disponível), duração 1–48 h, padrão 24 h. 96 ciclos de 15 minutos completam um dia. Iniciar/Pausar/Próximo passo/Reiniciar controlam a execução. Alterar velocidade preserva SOC, histórico e índice. Cada passo é atômico; pausa ocorre entre passos. Nunca acumular execuções atrasadas.
Velocidades: 60 s, 15 s (padrão) ou 7,5 s por ciclo. Se o computador demorar mais, o ciclo seguinte aguarda conclusão; não há execução concorrente. A validação batch remove esperas de parede, mas usa exatamente Engine.step.

## Origem e limites da simulação
Prédio e EV vêm dos CSVs oficiais de janeiro–junho, somente leitura. Histórico dos modelos termina no passo anterior; observações simuladas concluídas substituem os valores correspondentes apenas em memória/arquivos desta demo.
Conexões EVSE são uma representação agregada derivada de contagem e potência, com 22 kW por veículo; não reconstituem sessões individuais oficiais ou SOC de veículos. Demanda não atendida é registrada; não é convertida automaticamente em energia futura ou nova fila física.
Solar: irradiância sintética declarada, curva diurna 06–18h, pico 900 W/m² e variação determinística moderada na medição. Conversão usa irradiance_to_power e SolarConfig existentes (150 kWp, inversor125 kW), sem modificá-los. Não há consulta à internet, nem alegação de previsão meteorológica real ou teste independente.
Motor1, Motor2, MPC e Load Balancer são os existentes. SOC seguinte e comandos anteriores vêm do retorno do Motor3; BalancerState e connected_since persistem. Não há resposta específica a eventos implementada na UI.
Este é um simulador de passos com potência média constante por 15 minutos e bateria ideal segundo o modelo existente, não um gêmeo digital elétrico de alta frequência.

## Eventos
Agendar aplica no próximo passo. Duração configurável de 1–16 passos (padrão4).
Pico prédio: +160 kW; pico EV: demanda88 kW e quatro conexões, até6 chegadas no início; queda solar: medição ×0,15; falha EVSE: state=fault mantendo conexão física. Eventos expiram; não alteram forecasts futuros diretamente, parâmetros físicos ou decisões. Eventos repetidos do mesmo tipo não multiplicam amplitudes.
Execução batch usa eventos pré-declarados: 08h pico prédio, 12h queda solar, 15h pico EV, 15h15 falhaEVSE3. Não calibra modelos para favorecer resultados.

## Estado, auditoria e segurança
Cada sessão tem pasta UUID em outputs/simulation/sessions; Reiniciar cria outra pasta e preserva a anterior. Snapshots em state.json, ciclos completos em cycle_*.json e log estruturado events.jsonl. CSV acumulado disponível na UI.
Falha do runtime bloqueia e para a simulação sem avançar SOC. Setas tracejadas para EVSEs representam limites, não consumo individual. Fluxos contínuos representam energia calculada pelo runtime para demanda atendida.
Abrir execução de24h salva exibe resultados calculados anteriormente; não inicia novas decisões. Reiniciar retorna à execução interativa.
Nenhum comando é enviado a equipamentos, nenhum protocolo físico, LLM, cobrança ou backend é incluído. Remover demo/simulation e a opção correspondente de demo/app.py não afeta qualquer módulo src.

## Testes e artefatos
Core Python: python -B -m unittest discover -s demo/simulation/tests.
Demo Python: python -B -m unittest discover -s demo/tests.
outputs/simulation/v1 contém manifesto de preservação, cópia anterior do dashboard e run_24h com CSV, JSON, eventos, gráfico e resumo.
