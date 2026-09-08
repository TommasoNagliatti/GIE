"""Reproducible 12-hour example; no modifications or calls to Motors 1/2/3."""
import sys, json, csv, io, unittest, hashlib, os
from pathlib import Path
from datetime import datetime, timedelta
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from load_balancer import run_balancer, EVSEState

def main():
    out = ROOT / 'outputs/load_balancer/v1'
    out.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests/load_balancer'))
    stream = io.StringIO()
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (out/'test_results.txt').write_text(stream.getvalue(), encoding='utf-8')
    if not tests.wasSuccessful():
        raise RuntimeError('Tests failed; simulation aborted.')
    state = None
    rows, full, events = [], [], []
    start = datetime(2026, 8, 1, 7)
    blocks = [88,88,54,54,44,88,50,0,32,66,88,88]
    for k in range(48):
        t = start + timedelta(minutes=15*k)
        block = blocks[k//4]
        connected = [4 <= k < 40, 8 <= k < 44, 12 <= k < 36, 20 <= k < 48]
        arrivals = [4,8,12,20]
        devices = [EVSEState(f'EVSE{i+1}', connected[i],
                    state='fault' if i==2 and 24<=k<28 else 'available',
                    vehicle_max_kw=11 if i==1 and k<32 else None,
                    connected_since=start+timedelta(minutes=15*arrivals[i]) if connected[i] else None)
                    for i in range(4)]
        result, state = run_balancer(block, devices, t, previous=state)
        full.append(result);events.extend(result['events'])
        rows.append({key: result[key] for key in ['timestamp','ev_block_limit_kw','requested_total_kw','allocated_total_kw','evse_1_kw','evse_2_kw','evse_3_kw','evse_4_kw']})
    with (out/'simulation.csv').open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    for name,obj in [('simulation.json',full),('events.json',events),('example_output.json',full[12])]:
        (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(r['allocated_total_kw']<=r['ev_block_limit_kw'] for r in rows)
    assert all(0<=r[f'evse_{i}_kw']<=22 for r in rows for i in range(1,5))
    os.environ['MPLCONFIGDIR']=str(out/'.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    times=[datetime.fromisoformat(r['timestamp']) for r in rows]
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
    axes[0].stackplot(times,*[[r[f'evse_{i}_kw'] for r in rows] for i in range(1,5)],labels=[f'EVSE{i}' for i in range(1,5)],step='post',alpha=.8)
    axes[0].step(times,[r['ev_block_limit_kw'] for r in rows],where='post',color='black',ls='--',label='Limite do bloco')
    axes[0].set_ylabel('Potência total (kW)');axes[0].set_ylim(0,96)
    for i in range(1,5):axes[1].step(times,[r[f'evse_{i}_kw'] for r in rows],where='post',label=f'EVSE{i}')
    axes[1].axhline(22,color='black',ls=':',label='Máximo individual');axes[1].set_ylabel('Setpoint individual (kW)');axes[1].set_ylim(-1,24)
    for ax in axes:
        ax.axvspan(times[24],times[28],color='red',alpha=.08)
        ax.legend(loc='upper right',ncol=3,fontsize=8);ax.grid(alpha=.2)
    axes[0].annotate('EVSE3 em falha',xy=(times[24],55),fontsize=9,color='darkred')
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    axes[1].set_xlabel('Horário — cenário fictício de 12 horas')
    fig.suptitle('Load Balancer V1 — divisão justa com redistribuição')
    fig.tight_layout();fig.savefig(out/'simulation.png',dpi=150);plt.close(fig)
    manifest=json.loads((out/'preservation_before.json').read_text())
    changed=[p for p,h in manifest.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    summary=dict(tests_passed=tests.testsRun,randomized_cases=2000,cycles=len(rows),hours=12,
                 max_allocated_total_kw=max(r['allocated_total_kw'] for r in rows),
                 max_individual_kw=max(r[f'evse_{i}_kw'] for r in rows for i in range(1,5)),
                 block_limit_violations=0,protected_files_checked=len(manifest),protected_files_changed=changed,
                 events={code:sum(e['code']==code for e in events) for code in sorted({e['code'] for e in events})})
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
