"""Generate evidence indexes without changing any previous-phase artifact."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from gie_panel.alerts import Alerts,condition
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/panel/v1'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    before=json.loads((OUT/'preservation_before.json').read_text())
    after={p:digest(ROOT/p) if (ROOT/p).is_file() else None for p in before}
    changes=[dict(path=p,before=before[p],after=after[p]) for p in before if before[p]!=after[p]]
    (OUT/'preservation_after.json').write_text(json.dumps(dict(compared=len(before),unchanged=len(before)-len(changes),changes=changes),indent=2),encoding='utf-8')
    with tempfile.TemporaryDirectory() as temp:
        alerts=Alerts(Path(temp)/'events.sqlite')
        c=condition('EVSE_FAULT','Falha simulada de EVSE',equipment='EVSE3')
        alerts.observe('Commercial_HighAutonomy_V2','test-generation','2026-10-13T10:00:00-03:00','test-run:1',[c],{'energy'})
        alerts.ack('Commercial_HighAutonomy_V2',alerts.list('Commercial_HighAutonomy_V2')[0]['alert_id'])
        alerts.observe('Commercial_HighAutonomy_V2','test-generation','2026-10-13T10:15:00-03:00','test-run:2',[],{'energy'})
        alerts.observe('Commercial_HighAutonomy_V2','test-generation','2026-10-13T10:30:00-03:00','test-run:3',[],{'energy'})
        (OUT/'event_examples.json').write_text(json.dumps(alerts.history('Commercial_HighAutonomy_V2'),indent=2,ensure_ascii=False),encoding='utf-8');alerts.close()
    for args,name in [(['status','--short'],'git_status.txt'),(['diff','--stat'],'git_diff_stat.txt')]:
        r=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,check=True)
        (OUT/name).write_text(r.stdout or '(sem diferenças em arquivos rastreados; consulte git status para não rastreados)\n',encoding='utf-8')
    files=[ROOT/'src/gie_multistation/api.py',ROOT/'reports/provisioning/v1/four_stations.json',ROOT/'run_multistation_panel.bat']
    for base in [ROOT/'src/gie_panel',OUT]:
        files.extend(p for p in base.rglob('*') if p.is_file() and not any(x in p.parts for x in ['runtime','__pycache__']) and p.name!='inventory.json' and not p.name.startswith('launcher.'))
    inventory={str(p.relative_to(ROOT)).replace('\\','/'):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(set(files))}
    (OUT/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    print(json.dumps(dict(preserved=len(before)-len(changes),changed=changes,inventory_files=len(inventory)),indent=2))
if __name__=='__main__':main()
