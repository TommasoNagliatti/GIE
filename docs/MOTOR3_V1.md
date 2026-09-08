# Motor 3 V1 — gerenciamento de potência / MPC

Controlador local com `scipy.optimize.linprog(method="highs")`, somente variáveis contínuas. Não utiliza LLM nem API no controle. Os Motores 1 e 2 são importados apenas pelos adapters; seus códigos, dados, modelos e relatórios permanecem intactos.

## Uso

Com `src` no PYTHONPATH, a entrada pública é `motor_gerenciamento.run.run_control`. Recebe os DataFrames reais dos Motores 1/2, solar/tarifa/crédito (vetores de 48 valores ou Series com timestamps), `State`, medições e `Config`. A classe `FrozenForecastAdapters` carrega uma vez `MotorHibrido` e `MotorCarregadores` e chama suas funções reais `predict(history, origin)`.

```python
from motor_gerenciamento.run import run_control
from motor_gerenciamento.state import State, Measurements

resultado = run_control(
    previsao_predio, previsao_evs, solar_kw, tarifa, credito,
    State(battery_soc_pct=50), measurements=medicoes,
)
if resultado["execution_allowed"]:
    primeiro = resultado["first_decision"]  # só esta decisão pode ser aplicada
```

São exigidos 48 timestamps locais idênticos e contínuos de 15 minutos. As medições referem-se ao último intervalo completo. Na convenção dos Motores 1/2, uma linha histórica 07:45 só está disponível às 08:00, que é o primeiro timestamp da programação. Não há inferência implícita de valores ausentes.

`solver_status`, `solver_runtime_ms`, `fallback_used`, comandos da bateria, limite agregado EV, importação/exportação e SOC inicial/final aparecem no topo. `plan` contém os 48 passos; `first_decision` contém o primeiro, com `flows`. `events` e `llm_payload` são somente estruturas locais de dados.

## Formulação

Para t=0,...,47, Δ=0,25 h. Entradas: prédio B, solar S, demanda EV esperada D, potência alta Q, probabilidade de fila p, tarifa a e crédito b. Decisões não negativas: importação g, exportação x, carga c, descarga d, energia final E, EV servido v, limite EV L, excedente operacional o, demanda EV não atendida u, falta de margem z e déficit de reserva r.

Minimiza:

```text
Σ Δ [a·g − b·x
     + 1000·o
     + 100·(1+p)·u
     + 10·(1+p)·z
     + 2·r
     + 0,04·(c+d)
     + 0,001·(g+x)] + 5·r[47]
```

Os pesos são equivalentes monetários configuráveis, não tarifas reais. Os termos de potência são integrados em kWh; o déficit de reserva em kWh é penalizado por hora, com penalização terminal adicional. Pesos centralizados em `config.py`, pré-registrados antes dos testes e não ajustados com os resultados. É uma soma ponderada com prioridades fortes, não uma promessa de ordenação lexicográfica para qualquer tarifa arbitrária.

Restrições:

```text
S + g + d = B + v + c + x
E[t] = E_anterior + Δ·0,95·c − Δ·d/0,95
40 ≤ E[t] ≤ 190 kWh; E_anterior inicial = SOC_medido·200/100
0 ≤ c,d ≤ 100 kW
0 ≤ g ≤ 350 kW; 0 ≤ x ≤ 150 kW
0 ≤ v ≤ D; v ≤ L ≤ Q ≤ 88 kW
u = D − v
o ≥ g − 300; o ≥ 0
z ≥ Q − L; z ≥ 0
r ≥ 60 − E; r ≥ 0
```

O prédio nunca é variável controlável. Solar é uma entrada fixa integralmente utilizada; não há variável de corte. A fonte solar deve respeitar 125 kW AC; o sistema tem 150 kWp instalados. O limite de exportação 150 kW permite acomodar o excedente solar mesmo com bateria cheia.

### Capacidade Q90 fisicamente disponível

Não se adiciona Q90 ao balanço de consumo nem à energia da bateria. Com as potências planejadas da bateria mantidas, a importação líquida necessária se os EVs chegarem a L será:

```text
g − x + (L − v) ≤ 350
g − x + (L − v) ≤ 300 + o
```

Assim, a margem vem da redução de exportação e/ou espaço na rede, sem prometer descarga adicional de bateria não sustentada pelo SOC. `grid_capacity_over_target_kw` expõe o auxiliar o; `grid_over_target_kw` mostra o excedente do consumo esperado efetivo `max(g−300,0)`. O peso forte do alvo faz a margem Q90 ceder antes de induzir sobrecarga operacional.

### Política de utilização local e fluxos

Como política operacional adicional, EVs esperados recebem ao menos `min(D,max(S−B,0))`: não se deixa de atendê-los enquanto há solar excedente disponível. Impõe-se `d ≤ B+v−min(S,B+D)` para impedir descarga de bateria destinada a exportação e permitir a decomposição solicitada. Essas são políticas locais explícitas, não novos limites físicos.

O alocador usa solar → prédio → EV → bateria → rede; bateria → déficit do prédio → EV; rede → prédio → EV → carga da bateria. Confere somas por fonte/destino; fluxos não representam cabos separados.

Não há binários para exclusão de simultaneidade. Eficiência, custo de ciclagem e pequeno custo de fluxo da rede evitam soluções degeneradas. Todos os 48 passos são verificados; simultaneidade material acima de 0,00001 kW interrompe a execução, sem conversão automática para MILP. A V1 aceita tarifas não negativas e crédito de exportação não superior à tarifa de importação; estruturas de arbitragem fora desse escopo são rejeitadas.

## Segurança e fallback

Falhas do solver ou soluções inválidas acionam programação determinística, com prédio prioritário, solar integral, EV reduzível e bateria limitada pelo SOC disponível. Não há chamadas a GPT. Se não for possível estabelecer programação segura, retorna `execution_allowed=false`, plano vazio e evento crítico; não inventa atendimento de uma carga impossível. Exemplo explícito: prédio de 500 kW, sem solar, bateria no mínimo e rede limitada a 350 kW. Uma falha do fallback não prova por si só inviabilidade global de todo LP; indica ausência de programação segura obtida.

`dispatch.py` é uma guarda determinística de realização: recebe apenas o primeiro comando e as medições realizadas, limita bateria ao SOC, evita exportar descarga da bateria, cancela carga/usa descarga disponível/reduz EV quando necessário para a segurança física. Não reduz o prédio. Os ajustes ficam registrados como `SAFETY_OVERRIDE`. Não garante que erros arbitrários de previsão sejam sempre acomodáveis.

## Simulações e limitações

- 48h (15–16/06): previsões efetivamente recalculadas pelos Motores 1/2 congelados, histórico fornecido somente até o intervalo anterior; estado SOC atualizado após aplicar o primeiro comando.
- 72h fictícias: perfil de estresse pré-definido para demonstrar exportação, picos, limitação EV e uso de bateria.
- Em ambas, solar usa perfil determinístico fictício de 150 kWp limitado a 125 kW AC, entre 06h e 18h. Tarifa fictícia 0,35 fora de 17–21h e 1,20 nesse horário; crédito fictício 0,08. Não são valores Enel. A previsão solar coincide com a planta mock; não há teste de erro meteorológico nesta V1.
- O modelo de planta EV é agregado e exógeno: demanda solicitada, sessões e fila vêm do dataset, sem reagendar energia não atendida. A potência/energia efetivamente entregue é atualizada no histórico em memória, sem alterar CSVs. Uma simulação de sessões reagindo ao controle e a distribuição por carregador pertencem a etapas futuras.
- Os testes são de implementação e operação simulada, não certificação para acionar equipamentos reais. Tempos de solver excluem inferência dos Motores 1/2; os tempos de previsão também são salvos.

Resultados em `outputs/motor_gerenciamento/v1/`: testes, planos de 48 passos por ciclo, execução realizada, eventos, exemplos JSON completos, fallback e gráficos. A rotina de reprodução é `python -B src/motor_gerenciamento/demo.py`, com o interpretador do GIE.

SciPy 1.18.1 já está instalado. A dependência direta é declarada em `src/motor_gerenciamento/requirements.txt`, que inclui o requirements original sem modificá-lo.

Referência do solver: [documentação oficial SciPy/HiGHS](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html).
