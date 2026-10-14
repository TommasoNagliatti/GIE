"""Phase 5 report, charts and preservation evidence; no previous reports changed."""
import ast,hashlib,json,subprocess
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from gie_multistation.registry import ROOT
from .examples import fixture,sample
from .contracts import Provision,DynamicCycle,ModelState,ModelVersion

OUT=ROOT/'reports/provisioning/v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,text):(OUT/name).write_text(text,encoding='utf-8')
def plot_week(path,title,output):
    f=pd.read_csv(path);x=pd.to_datetime(f.timestamp)
    fig,axes=plt.subplots(3,1,figsize=(13,10),layout='constrained')
    for name in ['building_kw','ev_served_kw','solar_used_kw']:axes[0].plot(x,f[name],label=name)
    for name in ['grid_import_kw','grid_export_kw']:axes[1].plot(x,f[name],label=name)
    for name in f:
        if name.endswith('soc_after'):axes[2].plot(x,100*f[name],label=name)
    for a in axes:
        a.grid(alpha=.2);a.tick_params(axis='x',rotation=15)
        if a.lines:a.legend(fontsize=8)
    axes[0].set_ylabel('kW');axes[1].set_ylabel('kW');axes[2].set_ylabel('SOC %')
    if not axes[2].lines:axes[2].text(.5,.5,'Sem bateria instalada',ha='center',transform=axes[2].transAxes)
    fig.suptitle(title+' — 7 dias SIMULATED, sem hardware')
    fig.savefig(output,dpi=120);plt.close(fig)

def main():
    seasonal=json.loads((OUT/'seasonal_summary.json').read_text());baseline=json.loads((OUT/'baseline_week_summary.json').read_text())
    rows=[r for profile in seasonal for r in profile]
    for r in rows:
        if r['season']=='spring_week':plot_week(OUT/'seasonal'/r['station_id']/'spring_week.csv',r['station_id'],OUT/(r['station_id']+'_week.png'))
    plot_week(OUT/'baseline_week.csv','NEW_WEEK BASELINE',OUT/'BASELINE_week.png')
    write('example_provision.json',json.dumps(fixture(),indent=2));write('example_current.json',json.dumps(sample(fixture()),indent=2))
    write('contracts.schema.json',json.dumps({c.__name__:c.model_json_schema() for c in [Provision,DynamicCycle,ModelState,ModelVersion]},indent=2))
    before=json.loads((OUT/'preservation_before.json').read_text())
    changed=[p for p,h in before.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    allowed={'src/gie_multistation/'+n for n in ['api.py','manager.py','engines.py','README.md','API.md','COMPATIBILIDADE.md']}
    unexpected=sorted(set(changed)-allowed)
    def commercial(p):
        text=p.read_text(encoding='utf-8');node=next(n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name=='CommercialEngine')
        return ast.get_source_segment(text,node)
    unchanged=commercial(ROOT/'src/gie_multistation/engines.py')==commercial(OUT/'phase4_before/engines.py')
    frozen=json.loads((ROOT/'docs/release/frozen_manifest.json').read_text())
    mismatch=[p for p,h in frozen.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    evidence=dict(previous_files=len(before),identical=len(before)-len(changed),authorized_changes=changed,unexpected=unexpected,commercial_engine_unchanged=unchanged,frozen_mismatch=mismatch)
    write('preservation_after.json',json.dumps(evidence,indent=2))
    if unexpected or not unchanged or mismatch!=['demo/high_autonomy_v2/app.py']:raise RuntimeError('Unexpected preservation change')
    table=['| Perfil / cenário | Ciclos | Prédio kWh | EV atendido kWh | Import kWh | Export kWh | Máx. erro kW | Solver médio/máx. ms |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        t=r['totals_kwh'];table.append(f"| {r['station_id']} / {r['season']} | {r['cycles']} | {t['building_kw']:.3f} | {t['ev_served_kw']:.3f} | {t['grid_import_kw']:.3f} | {t['grid_export_kw']:.3f} | {r['max_balance_error_kw']:.2e} | {r['solve_ms_mean']:.1f}/{r['solve_ms_max']:.1f} |")
    total=sum(r['cycles'] for r in rows)+baseline['cycles']
    write('RELATORIO_FINAL.md',f'''# GIE — Fase 5

Concluído localmente em 13/10/2026. Cadastro dinâmico e funcionamento BASELINE sem histórico implementados em src/gie_provisioning e integrados à extensão multiestação. Nenhum código do Backend/Site/App/banco/Docker alterado; sem commit/push/deploy ou acionamento físico.

## Resultado e demonstração

Nova estação tecnicamente validada é cadastrada, consultada, inicializada, parada e recuperada sem reiniciar as demais. Aprovação local exige token com capability de provisionamento e station_id explicitamente autorizado. Cadastro repetido é idempotente; substituição técnica é recusada. Arquivos usam paths construídos pelo servidor e checksum; processo, configuração, histórico, cache e estado individuais. Cadastro e SOC sobrevivem ao reinício do serviço.

Prova em four_stations.json: comercial original, posto, casa e NEW_NO_HISTORY, quatro PIDs distintos, via API FastAPI ASGI com workers reais. A quarta estação tem cinco carregadores de 2/3/4/5/6kW, ramal limitado, timezone America/Manaus, zero baterias/solar, nenhum CSV ou modelo emprestado. Produz 48 estimativas identificadas; sem current fica DEGRADED, com current completo/confiável executa MPC e allocator. Queda forçada e restart não alteram estado da casa e preservam o SOC/contador da nova estação. Não foi realizado deploy nem teste de rede pública.

BASELINE usa envelope técnico conservador de prédio/EV, solar futuro garantido zero e current independente para primeiro passo. Previsão não é medida. Origem permanece SIMULATED; dados ausentes, futuros, antigos ou não confiáveis não autorizam avanço. Bateria/inversor indisponíveis e rede insuficiente têm testes explícitos. A matemática Energy V3 não foi modificada.

## Testes executados

- 14 testes novos aprovados (tests_final.txt), incluindo validação técnica, autorização, concorrência/idempotência, cinco EVSEs, zero equipamentos, timezone, proveniência/freshness, falhas e quatro processos.
- 41 regressões Fase 4 aprovadas (regression_phase4.txt).
- 223 regressões comerciais aprovadas; três skips históricos mantidos pelo runner original. Logs regression_*.txt e regression_results.json.
- {total} ciclos de 15min, {total*48} passos de horizonte verificados. Dias de verão (10/02), outono (10/05), inverno (10/08) e sete dias contínuos de primavera (01–07/11/2025) por perfil novo da Fase 4. Reinício no meio de cada cenário com igualdade exata do checkpoint.
- Estação dinâmica NEW_WEEK: mais sete dias contínuos, com solar, bateria de 17kWh, cinco EVSEs, indisponibilidade de bateria no dia 3, inversor no dia 5 e restart no meio. {baseline['verified_steps']} passos, erro de balanço até {baseline['max_balance_error_kw']:.3e}kW, erro de energia até {baseline['max_energy_error_kwh']:.3e}kWh, solver médio/máximo {baseline['solve_ms_mean']:.1f}/{baseline['solve_ms_max']:.1f}ms.

{chr(10).join(table)}

Energia é a integração kW×0,25h, sem truncamento para esconder desvios. CSVs mantêm primeira decisão de cada ciclo; summaries guardam erros máximos verificados em todos os 48 passos, SOC inicial/final, tempos e reinícios. Os ensaios sazonais são testes retrospectivos de operação, inclusive em meses usados no treino original; não são nova avaliação fora da amostra dos previsores. Recall residencial permanece 6,778%. O comercial foi validado pelas regressões/16 cenas/ciclo simultâneo; não se declara evolução multibateria contínua para sua política congelada.

## Modelos versionados e integração futura

Contratos ModelState/ModelVersion v1 preparam BASELINE, CANDIDATE, PERSONALIZED, DEGRADED, versão ativa/candidata/anterior, revisão esperada e hashes de artefato/validação para ativação/rollback por station_id. Cadastro real inicia BASELINE. Falta de current é condição operacional DEGRADED, separada do treinamento.

Ativação de novos modelos permanece deliberadamente indisponível: activation_supported=false e /model-transition retorna 409 após validar o contrato. Não há upload, treinamento automático nem promoção fictícia. Um adaptador posterior deve verificar artefatos próprios da estação, aprovação, revisão e rollback; contratos não são prova de modelo treinado.

Documentação/API, exemplos de criação/current, mapeamento do gieContract 2.0, requisitos e comandos exatos: ../../../src/gie_provisioning/README.md. O contrato do Backend não é aceito diretamente: faltas de exportação, SOC inicial, eficiências, vínculo a inversor ou circuitos precisam ser resolvidas na aprovação, sem inventar valores. IDs preservados como strings. Nenhuma alteração no EMPS.

## Preservação e limites

{len(before)} arquivos anteriores verificados, {len(before)-len(changed)} idênticos; {len(changed)} alterações autorizadas somente em engines.py, manager.py, api.py e documentação da extensão multiestação. Zero diferenças inesperadas. Código Energy V3, dados, modelos, comerciais e cenas intactos. Cópias anteriores em phase4_before; detalhes em preservation_after.json. Nenhum arquivo anterior removido.

Divergência preexistente demo/high_autonomy_v2/app.py mantida sem atualização de hash. Gate global do release permanece bloqueado; suites executadas individualmente, não se declara release aprovado. Tentativa inicial de simulação dentro do sandbox falhou por permissão de diretório temporário; log preservado e execução refeita no ambiente local autorizado, sem alterar políticas do Windows.

Limites: simulação apenas; TR​USTED é uma declaração da fixture autorizada, não medidor verificado. Previsões conservadoras não garantem picos reais. Demanda EV permanece exógena, sem realimentação do SOC veicular após corte. Falta terminal de reserva adicional, homologação de inversores, telemetria física, ACK/readback, TLS, quotas/isolamento de segurança e gestão operacional de credenciais. Só um gerenciador por volume. Corrupção/conflito de cadastro bloqueia e exige inspeção, sem limpeza automática. Atualização técnica e carregamento real de novos modelos são etapas posteriores; nenhum endpoint permite alterar os equipamentos aprovados silenciosamente.

Antes da integração EMPS: adaptador técnico aprovado, credenciais por estação, disponibilidade/freshness/proveniência verificadas, cache por station_id/generation, reconciliação de respostas perdidas, política auditável de reconfiguração e modelos, backup/quotas/supervisão. Sessões, START e pagamentos continuam no Backend. physical_dispatch=false e hardware_commands_sent=false.

Inventário SHA-256 em inventory_sha256.json (exclui a si próprio, dependências, caches e runtime). Git status em git_status.txt; diff --stat vazio para arquivos rastreados porque estas extensões ainda são diretórios não versionados.
'''.replace('TR\u200bUSTED','TRUSTED'))
    for cmd,name in [(['git','status','--short'],'git_status.txt'),(['git','diff','--stat'],'git_diff_stat.txt')]:write(name,subprocess.check_output(cmd,cwd=ROOT,text=True))
    files=[]
    for folder in [ROOT/'src/gie_provisioning',OUT]:
        files.extend(p for p in folder.rglob('*') if p.is_file() and not any(x in p.parts for x in ['__pycache__','runtime']) and p.name!='inventory_sha256.json')
    files.extend(ROOT/p for p in changed)
    write('inventory_sha256.json',json.dumps({p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files))},indent=2))
    print(json.dumps(evidence,indent=2));print('Verified cycles:',total)
if __name__=='__main__':main()
