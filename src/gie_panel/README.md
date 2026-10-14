# Painel GIE — Fase 5.5

## Abrir no Windows

Dê dois cliques em `C:\goodwill_ai\GIE_DATASETS\run_multistation_panel.bat`.
O navegador abre em **http://127.0.0.1:8504**. Mantenha a janela aberta; Ctrl+C encerra os serviços iniciados por ela.

- Interface nova: 8504; API autenticada: 8520; painel original: 8503.
- Se 8503 já estiver ocupada, o launcher preserva o serviço existente. Nesta máquina foi identificado o High Autonomy V2 original nessa porta.
- Se 8504/8520 estiverem ocupadas, o launcher não encerra processos. Se o painel já está rodando, abra o endereço acima.
- Nada é instalado, apagado ou enviado para hardware pelo launcher. Não há dependência do EMPS/MySQL.

Ambientes existentes: `C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe` para API/MPC e `.venv-demo\Scripts\python.exe` para Streamlit. Em outro computador, configure `GIE_CORE_PYTHON` e `GIE_DEMO_PYTHON` para ambientes equivalentes. Dependências da API nas Fases 3–5; dependências de UI em `requirements-ui.txt`. A interface não importa nem executa MPC.

## Operação

1. Selecione prédio, posto, residência ou BASELINE.
2. **Replay salvo**: lê evidências já existentes; próximo/reproduzir/pausar/reiniciar nunca executam decisões nem geram alertas.
3. **Simulação interativa**: inicialize/retome ou escolha **Novo teste isolado**. O novo teste usa o cenário selecionado e um diretório exclusivo. Avance um ciclo ou reproduza até 96 ciclos de 15 min. Velocidade visual não altera o passo energético.
4. Trocar cenário não reseta silenciosamente um teste em andamento: a interface avisa quando o cenário ativo é diferente. Use Novo teste isolado para trocar.
5. Prédio: abra Presentation / Manual Demo e aplique o modo. As 16 cenas originais, anterior/próxima, pausa, loop e intervalos 5/10/15s usam o controle original na API. Eventos Manual Demo são os eventos já existentes.
6. BASELINE: entrada normal, ausente, antiga, sobrecarga ou EVSE indisponível; somente entradas simuladas. Retorne a normal para observar recuperação.
7. Reconhecer um aviso não resolve a condição. A recuperação requer duas observações válidas distintas; reinícios e ausência de telemetria não apagam falhas.

## Dados e segurança

`reports/panel/v1/runtime/` contém SQLite de alertas, índice dos testes e checkpoints isolados. É ignorado pelo Git. Reset cria outro ID de teste; diretórios anteriores são mantidos. Reinício recupera checkpoints matemáticos, mas não publica a decisão anterior como atual: execute um novo ciclo. Os gráficos indicam UTC; respostas mantêm o fuso original.

API e UI escutam somente loopback. O launcher gera credencial efêmera em memória, enviada à API pelo servidor Streamlit; nunca pela URL ou JavaScript do navegador. A credencial tem escopo explícito nas quatro estações. Não exponha esse painel local à internet.

`physical_dispatch=false`, `hardware_commands_sent=false`, `commands_valid=false`. `execution_allowed` é validade matemática, não autorização física. Limite autorizado não é consumo medido. Ausência de dados aparece como “—”.

O comercial tem um **banco agregado** no contrato original; não foram inventadas baterias individuais. Posto tem BAT_01/BAT_02; casa não tem bateria; BASELINE tem cinco EVSEs e nenhuma bateria. Solar futuro indisponível não é mostrado como previsão zero.

Replay primavera do posto/casa possui planos de 48 passos. Replays das outras estações do ano guardaram primeiras decisões, sem previsões: a UI explicita essa limitação. BASELINE salvo possui um ciclo; interativo permite até 96. Previsão EV residencial mantém aviso de baixa confiabilidade. Todas as séries são sintéticas/simuladas.

## Testes

No PowerShell, na raiz do projeto:

```powershell
$env:PYTHONPATH="$PWD\src;$PWD\src\gie_multistation\.deps"
$env:PYTHONUTF8='1'
& 'C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe' -B -m unittest gie_panel.test_panel -v
& 'C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe' -B -m gie_panel.ui_fixtures
& 'C:\Users\Tommaso\Desktop\Gie\.venv-demo\Scripts\python.exe' -B -m unittest gie_panel.test_ui -v
& 'C:\Users\Tommaso\Desktop\Gie\.venv\Scripts\python.exe' -B -m gie_panel.regression
```

Use o wrapper `gie_panel.regression`: o teste original da Fase 5 possui uma escrita fixa de relatório; o wrapper a redireciona para a Fase 5.5. Não execute diretamente esse teste quando quiser preservar evidências históricas.
