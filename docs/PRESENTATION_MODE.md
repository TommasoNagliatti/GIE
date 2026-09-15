# Presentation Mode V1

Abra `run_high_autonomy_v2.bat`, porta 8503, perfil High Autonomy V2, área Presentation.
A comparação V1 × V2 continua disponível e usa os mesmos arquivos históricos.

São 16 cenas independentes, não uma nova simulação contínua de 24h. Cada cena fornece
telemetria e previsões demonstrativas explícitas ao runtime/MPC/Load Balancer V2
congelados. Solar e EV previstos ficam constantes; picos de prédio acima de 200 kW
duram um intervalo e voltam a 200 kW. Não são previsões novas dos Motores 1/2.
O SOC é uma medição escolhida para cada situação, não a continuação da cena anterior.

Sequência: madrugada; rede backup; amanhecer; solar atende prédio; chegada EV;
excedente; forte geração; exportação; queda solar; pico prédio; pico EV;
pico combinado; falha EVSE3; recuperação; SOC mínimo; noite.

Os resultados foram produzidos pelo core real e validados antes do replay.
Entradas, resultados e expected_behaviors: `src/gie_control/assets/scenes.json`.
Gerador de novas cenas: `tools/build_presentation.py`; recusa sobrescrever a biblioteca existente.
Nenhum histórico, modelo ou parâmetro MPC é modificado.

Autoplay: 5/10/15 segundos, padrão 10, pausa/retoma, anterior/próxima/reset e loop.
O relógio é monotônico; cada tick avança no máximo uma cena, sem recuperar atrasos em rajada.
O host chama `GIEControl.tick()` periodicamente; não existe scheduler interno.

Manual Demo altera entradas e executa novamente o core congelado. O dashboard usa
o Python de `.venv` por subprocesso, sem instalar SciPy/ML em `.venv-demo`.
Cada instância de controle é por sessão. Histórico limitado às últimas 100 mensagens.
Eventos e previsões são identificados como demonstração. Nenhuma rede é usada nessas cenas.
