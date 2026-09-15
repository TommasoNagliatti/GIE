# Bundle regenerável

Na raiz GIE, execute `.venv\Scripts\python.exe -B tools\build_integration_bundle.py`.
Saída: `dist/GIE_Integration`. O builder recusa sobrescrever bundles existentes;
use `--output dist/GIE_Integration_novo` para gerar outra revisão.

Inclui API `gie`, fontes de inferência necessárias, MPC/Load Balancer/runtime, previsão solar,
controle, mensagens, visual_state, biblioteca das 16 cenas, perfil, modelos efetivamente usados,
requirements, INTEGRATION.md e VERSION.json com hashes.

Não inclui venv, datasets, EnergyPlus, Streamlit, screenshots, simulações históricas,
testes, Git, caches, train.py ou evaluate.py. Helpers de treino/auditoria e CLI são
removidos da cópia exportada das features por AST; corpos de inferência são preservados.
Fontes originais permanecem intactas. VERSION.json explicita essa extração verificável.
O bundle preserva `src/` para manter os caminhos dos modelos existentes.

Presentation funciona offline. NORMAL exige históricos do caller e a previsão solar
do provider configurado (padrão Open-Meteo/cache/fallback). O bundle não traz históricos.
Sem backend comercial, servidor HTTP, hardware, pagamento ou autenticação.
