# Observabilidade e demo V1
Camada opcional em src/observabilidade. build_trace(cycle, previous) extrai evidências; run_observed_cycle envolve o runtime existente sem alterar sua matemática. previous é o trace anterior. Estado inicial desconhecido permanece null; não é inventado como zero. changes contém somente mudanças com referência conhecida.
Reason codes registram condições numéricas e eventos nativos, não demonstram causalidade interna do solver. llm_context é compacto e determinístico; nenhuma chamada a LLM. O trace completo conserva health, eventos e fluxos.
DecisionLog persiste JSONL, flush/fsync e deduplicação por trace_id. Usar um arquivo por escritor/sessão. Não é um banco transacional multi-processo. Falha de escrita aparece em logging_error, sem alterar decisão do core.

## Demonstração
Execute run_demo.bat e abra http://localhost:8501.
Ambiente separado .venv-demo; requirements-demo.txt contém apenas Streamlit, com dependências transitivas necessárias. O inicializador não instala nada. O core usa .venv original.
Replay contém oito cenários ilustrativos independentes, incluindo bateria, falha EVSE, exportação e bloqueio. Dados e clima são gravados; não há internet. Saltos de SOC não representam evolução física contínua.
Live Demo executa modelos reais e run_gie_cycle no Python do core, com clima atual/cache/fallback. Histórico é deslocado de junho; medições são fixtures sintéticas. Não é telemetria real nem avaliação preditiva. Cache e resultados Live ficam exclusivamente em outputs/observabilidade/live.
Próximo intervalo avança 15 minutos demonstrativos; Auto Play Replay tem mínimo 3 segundos, Live mínimo 30 segundos e limite 48 chamadas por sessão. Reset não remove limite temporal Live. Nenhum equipamento recebe comando.

## Remoção e reprodução
demo/, requirements-demo.txt, run_demo.bat e .venv-demo podem ser removidos sem efeito nos motores. src não importa Streamlit. Não há frontend comercial, usuários, cobrança ou backend GoodWe.
Testes core: .venv/Scripts/python -B -m unittest discover -s tests/observabilidade
Testes UI: .venv-demo/Scripts/python -B -m unittest discover -s demo/tests
Dependências exatas transitivas registradas em demo/requirements-demo-lock.txt.
Manifestos e relatório de preservação ficam em outputs/observabilidade/v1.
