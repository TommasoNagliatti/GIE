"""Publish a reproducible Markdown report from validated results, never estimates."""
import json,hashlib
from pathlib import Path
from gie_panel.comparison import OUT,ROOT,summarize,atomic

def main():
    result=json.loads((OUT/'result.json').read_text(encoding='utf-8'))
    # Recompute presentation summaries from unchanged raw trajectories. Preserve
    # the original run artifact and all MPC checkpoints, never rerun the engine.
    for p in result['periods'].values():
        p['summary']={v:summarize(rows) for v,rows in p['rows'].items()}
    result['summary_version']=2
    atomic(OUT/'result.json',result)
    old=json.loads((OUT/'preserved_hashes.json').read_text(encoding='utf-8-sig'))
    changed=[x['Path'] for x in old if hashlib.sha256(Path(x['Path']).read_bytes()).hexdigest().upper()!=x['Hash']]
    if changed:raise ValueError('Preservation mismatch: '+repr(changed))
    monthly=result['periods']['Novembro · 30 dias'];a=monthly['summary']['A'];b=monthly['summary']['B']
    lines=['# GIE · Comparador residencial e fluxo visual','',f'Execução `{result["run_id"]}`. SIMULAÇÃO: nenhum comando físico.','',
           '## Resultado energético', '',
           f'Em novembro, a bateria reduziu a importação de **{a["import_kwh"]:.2f} para {b["import_kwh"]:.2f} kWh**: diferença de **{a["import_kwh"]-b["import_kwh"]:.2f} kWh**. Isso é benefício energético no cenário simulado, não comprovação de retorno financeiro.', '',
           '| Período | Rede A (kWh) | Rede B (kWh) | Exportação A/B (kWh) | Perdas B (kWh) | Ciclos B | Pico A/B (kW) |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for name,p in result['periods'].items():
        x,y=p['summary']['A'],p['summary']['B']
        for v in ('A','B'):assert summarize(p['rows'][v])==p['summary'][v]
        lines.append(f'| {name} · {p["start"]}–{p["end"]} | {x["import_kwh"]:.2f} | {y["import_kwh"]:.2f} | {x["export_kwh"]:.2f} / {y["export_kwh"]:.2f} | {y["loss_kwh"]:.2f} | {y["equivalent_cycles"]:.2f} | {x["peak_grid_kw"]:.2f} / {y["peak_grid_kw"]:.2f} |')
    lines+=['','| Balanço mensal | A: sem bateria | B: com bateria |','|---|---:|---:|']
    for key,label in [('solar_kwh','Solar disponível kWh'),('building_kwh','Casa kWh'),('ev_requested_kwh','EV solicitado kWh'),('ev_served_kwh','EV atendido kWh'),('solar_direct_kwh','Solar direto nas cargas kWh'),('charge_kwh','Solar para bateria, AC kWh'),('discharge_kwh','Bateria para cargas, AC kWh'),('curtailed_kwh','Solar limitado kWh'),('initial_kwh','Armazenamento inicial kWh'),('final_kwh','Armazenamento final kWh'),('limited_intervals','Intervalos EV limitados')]:lines.append(f'| {label} | {a[key]:.2f} | {b[key]:.2f} |')
    lines+=['',
       '## Como interpretar', '',
       'A bateria desloca parte do excedente solar para outros horários. Ela não cria energia: há perdas e diferença entre energia armazenada no começo e no fim. O efeito sobre o pico da rede depende do horário das cargas e do SOC, não apenas da capacidade nominal.',
       'Novembro é um mês completo de avaliação dos dados sintéticos de 2025, não uma extrapolação anual. Os dias com/sem EV são os primeiros dias correspondentes encontrados no dataset desse mês; a semana é 1–7/11. Todos são recortes da mesma trajetória mensal, com SOC herdado dos dias anteriores explicitamente apresentado. Não se reinicia a bateria em cada gráfico.',
       'Novembro já era o mês de referência do replay de primavera, escolhido antes de observar o benefício da bateria. Contexto do dataset anual: casa 231,63 kWh no mês versus média mensal 232,88; solar 768,57 versus 691,76; EV 52,70 versus 63,04. É representativo de um mês de primavera com três recargas, mas tem mais sol e menos EV que a média anual. Não representa todas as estações. Totais dos 12 meses em `contexto-mensal-dataset.json`.',
       'Sem tarifas de compra/exportação fornecidas para este experimento e sem custos da instalação: nenhuma economia monetária ou payback foi calculado.', '',
       '## Hipótese técnica e compatibilidade', '',
       'Bateria LX U5.4-20 como referência: 5,4 kWh, 47,5–57,6 V, 50 A. Simulação conservadora: SOC 20–95%, janela 4,05 kWh, 2,2 kW AC de carga/descarga, eficiência assumida 95% em cada sentido. O limite considera 2,2/0,95 < 47,5×50/1000. Início do mês em SOC mínimo: não há energia inicial utilizável gratuita. A eficiência é hipótese de sistema, não garantia de fabricante.',
       'O inversor já registrado é GW6000-ES-20, ES G2, 6 kW, 120 A (não a variante M). A lista oficial permite a combinação de família LX U5.4-20/ES G2 com ARM ≥02. Ainda requer validação do equipamento exato, firmware, SKU regional, BMS, cabeamento, proteções e projeto elétrico. Não é projeto certificado nem recomendação de compra.',
       '[Bateria: ficha oficial AU](https://en.goodwe.com/Ftp/Downloads/Datasheet/AU/GW_Lynx%20Home%20U%20Series%20%28LV%29_5.4-20_Datasheet-AU.pdf) · [Inversor: ficha oficial EMEA](https://es.goodwe.com/Ftp/Downloads/Datasheet/EMEA/GW_ES%20G2_Datasheet_EMEA-EN.pdf) · [Compatibilidade GoodWe V029.1](https://us.goodwe.com/Ftp/EN/Downloads/User%20Manual/GW_Battery%20Compatibility%20Overview-EN.pdf). Consultados em 14/10/2026.',
       'A conexão simulada mantém rede 17 kW, exportação 6 kW, PV 5,5 kWp e EVSE 7 kW. Os 17 kW são o limite da instalação; não são capacidade de passagem pelo inversor. Não foram modeladas todas as cargas na saída backup.', '',
       '## Método e validação', '',
       'Nenhum corte EV material foi observado. Resíduos máximos de 0,00004 kW decorrem da tolerância lexicográfica; a contagem visual de cortes usa >0,0001 kW (0,1 W). Os valores brutos e integrais são preservados. O resumo v2 foi derivado das trajetórias originais sem reexecutar ou alterar o MPC.',
       'Energy V3 real, 48 passos de previsão, 15 minutos por ciclo e decisão aplicada somente ao primeiro passo. Mesmos modelos, datasets, timestamps e previsões causais; solar futuro usa o baseline do dia anterior do runtime. Sem retreino ou alteração da matemática.',
       'O limite conservador do Energy V3 solar utilizado + carga + descarga ≤6 kW permanece intacto. Resultados dependem das previsões existentes, incluindo baixa confiabilidade de eventos EV residenciais; não são otimização com futuro perfeito.',
       'Balanço AC: solar utilizado + importação + descarga = casa + EV atendido + carga + exportação. Solar disponível = utilizado + limitado. Armazenamento: ΔE = 0,25×(0,95×carga − descarga/0,95). Perdas = 0,25×[0,05×carga + (1/0,95−1)×descarga]. Ciclos equivalentes = descarga DC acumulada / 5,4 kWh nominal.',
       'Solar direto = utilizado − exportado − enviado à bateria. Carga da bateria é exclusivamente solar nesta política; descarga não é contada outra vez como solar direto. Trata-se de atribuição contábil do barramento, não rastreamento físico de elétrons.',
       f'{result["cycles_per_case"]} ciclos por cenário; máximo erro de balanço nos horizontes: {result["max_guard_balance_error_kw"]:.3g} kW. Checkpoints independentes: '+str(result['checkpoint_paths'])+'.',
       f'Preservação: {len(old)} arquivos verificados por SHA-256, sem alterações (motor Energy V3, modelos treinados e datasets). Cadastro oficial da residência continua sem bateria.', '',
       '## Interface e arquivos', '',
       '- Alterados: `src/gie_panel/app.py` e `service.py` (apresentação e endpoint residencial de leitura).',
       '- Novos: `flow.py`, `comparison.py`, `comparison_ui.py`, `comparison_report.py`, testes `test_comparison.py` e `test_comparison_ui.py`.',
       '- Fluxo com setas somente em potências positivas, cores e rótulos grandes; baterias individuais. Casa oficial sem nó de bateria. Acumulados apenas em históricos consecutivos NORMAL/REPLAY; cenas avulsas não são integradas.',
       '- Comparador com eixos iguais por par, SOC/energia/perdas separados, CSV para download, quatro períodos e tabela de balanço.',
       '- Artefatos nesta pasta: resultados JSON, CSVs A/B, checkpoints, logs de testes e capturas. Nenhum commit/push/deploy; EMPS, matemática, modelos comerciais e alertas não foram editados.', '',
       '## Testes executados', '',
       '22 testes distintos aprovados: 10 testes preexistentes de API/isolamento/avisos/16 cenas, 4 do fluxo visual, 5 das evidências energéticas e preservação, 1 da autorização do comparador e 2 de interface Streamlit (quatro estações, quatro períodos, retorno ao painel). O teste preexistente que grava `interactive_96.json` teve a evidência original preservada por cópia e restaurada com o mesmo SHA-256; a nova execução está em `interactive_96-regression.json` nesta pasta.',
       '5.760 ciclos MPC reais, 2.880 em cada cenário. Integração kW×0,25 h, balanço AC e armazenamento, limites de SOC/potência/rede, igualdade dos dados de entrada e hashes dos modelos/datasets verificados. Os resíduos EV do solver ficaram abaixo de 0,1 W; energia bruta não foi truncada.',
       'Logs: `tests-interface-api.txt`, `tests-energy.txt`, `tests-ui-final.txt`. Avisos não bloqueantes: depreciação httpx/Starlette do ambiente existente e ScriptRunContext do AppTest. Não houve falhas.', '',
       '## Validação visual e capturas', '',
       'Painel real em localhost:8504 validado em 1440×1000 e 900×900. Na largura menor, cartões e pares de gráficos quebram em linhas sem cortar os valores. A residência oficial não desenha bateria; o posto mostra BAT_01 e BAT_02 separadas, com seta apenas na bateria ativa.',
       '- [Resumo mensal](comparacao-mensal.png)',
       '- [Dia com EV](comparacao-dia-ev.png)',
       '- [SOC e armazenamento](soc-armazenamento.png)',
       '- [Posto com duas baterias](posto-duas-baterias.png)',
       '- [Casa sem bateria](residencia-sem-bateria.png)',
       '- [Cartões responsivos](comparacao-responsiva.png) e [gráficos responsivos](graficos-responsivos.png)', '',
       '## Iniciar no Windows', '',
       '```bat','cd /d C:\\goodwill_ai\\GIE_DATASETS','run_multistation_panel.bat','```','',
       'Abra http://127.0.0.1:8504 → Residência → **Comparar baterias**. A leitura dos resultados já calculados é imediata; não executa novo MPC por clique. Mantenha a janela do launcher aberta. Se as portas já estiverem ocupadas, use o painel que já está rodando.', '',
       'Para repetir o experimento, em PowerShell (cada execução cria uma pasta nova):','```powershell', 'cd C:\\goodwill_ai\\GIE_DATASETS', '$env:PYTHONPATH="$PWD\\src;$PWD\\src\\gie_multistation\\.deps"', "& 'C:\\Users\\Tommaso\\Desktop\\Gie\\.venv\\Scripts\\python.exe' -B -m gie_panel.comparison", "& 'C:\\Users\\Tommaso\\Desktop\\Gie\\.venv\\Scripts\\python.exe' -B -m gie_panel.comparison_report", '```', '',
       'Uma simulação mensal pode levar vários minutos. O painel publica somente resultados completos. Experimentos anteriores ficam em `runs/`; `result.json` aponta para a última execução concluída. Testes de evidências falham se o resultado não existir (não fabricam uma fixture).', '',
       '## Limitações', '',
       'Dados sintéticos e um mês analisado; degradação, envelhecimento, temperatura da bateria e custos não simulados. Certificação da instalação e retorno financeiro não demonstrados. No celular, use o botão de tela cheia do diagrama para ampliar os rótulos.']
    (OUT/'RELATORIO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (OUT/'preservation_result.json').write_text(json.dumps(dict(checked=len(old),changed=changed)),encoding='utf-8')

if __name__=='__main__':main()
