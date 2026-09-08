# Commercial High Autonomy V2
Revisão separada, com perfil fixado antes dos resultados:800 kWp DC /500 kW AC; bateria2000 kWh ±450 kW; SOC20–95%; EV88 kW; rede350 kW; exportação500 kW; eficiências0,95. SOC inicial50% nos dois perfis. Nada da V1 foi sobrescrito.

## Política matemática
MPC linear de48 passos Δt=0,25h. Reutiliza as equações físicas:
E[t+1]=E[t]+Δt*(ηc*C[t]−D[t]/ηd).
400≤E≤1900 kWh; C,D≤450 kW.
C[t]≤max(0,PV[t]−prédio[t]−EV_esperado[t]).
Solar must-use, sem curtailment, sem carga pela rede e sem exportação da bateria.
Objetivos lexicográficos, mantendo cada ótimo anterior por restrição (tolerância1e-7):
1. EV não atendido;
2. kWh importados em todo o horizonte;
3. importação atual;
4. exportação total;
5. exportação atual;
6. throughput da bateria apenas como desempate de soluções degeneradas;
7. déficit de headroom Q90 sem prejudicar prioridades anteriores.
Não há reserva, objetivo terminal de SOC, custo de SOC baixo ou custo econômico de desgaste. O desempate não pode economizar ciclos sacrificando atendimento, importação ou armazenamento solar. O campo legado reserve_pct=0 e reserve_deficit=0 servem apenas ao layout reutilizado; a restrição de reserva fica redundante.
Medições atuais entram no passo zero do MPC e na projeção física original. Não há regra local de descarregar tudo. Necessidades físicas de viabilidade futura podem restringir trajetória; não são reserva estratégica.
Falha do solver interrompe V2, sem apresentar fallback V1 como nova política.

## Reutilização
runtime_adapter reutiliza o mesmo objeto de código da função congelada por FunctionType, com cópia local do dicionário de dependências. Não altera globals originais nem duplica fonte da orquestração. Só política e validação do envelope solar são substituídas localmente. Integração solar original continua125 kW.
Dashboard V2 possui entrada própria e seletor V1/V2, preservando dashboard atual; reproduz decisões salvas e não reimplementa MPC.

## Comparação e fórmulas
Mesmos96 timestamps, prédio, EVs, estadosEVSE, eventos e previsões salvas dos Motores1/2. Escala-se somente usina e inversor no mesmo perfil de irradiância/nuvens. Não há retreinamento nem realimentação diferente das previsões por alteração da bateria. Não é novo teste de acurácia.
Energia total consumida = prédio + EV atendido; exclui carga da bateria e perdas.
Solar autoconsumido = solar gerado − exportado; inclui armazenamento e perdas, não só consumo final direto.
autossuficiencia_pct =100*(1−energia_importada_rede_kwh/energia_total_consumida_kwh).
SOC inicial igual representa100 kWh armazenados na V1 e1000 kWh na V2. Portanto a comparação muda dimensionamento e política; não isola só a política e não comprova autonomia anual. Resíduos de importação abaixo1e-9 são exibidos como zero. Nenhum ajuste foi feito após observar o gráfico.
Iniciar: run_high_autonomy_v2.bat, porta8503. Artefatos: outputs/high_autonomy_v2/comparison.
