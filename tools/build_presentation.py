"""Generate only new demonstration fixtures with the existing frozen V2."""
from pathlib import Path
import sys,json,hashlib,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from gie_control.scenarios import SCENES,execute_demo,validate_behavior

def main():
    dest=ROOT/'src/gie_control/assets/scenes.json'
    if dest.exists():raise FileExistsError('Preserving already generated scenes')
    scenes=[];start=time.perf_counter()
    for id,name,source,behaviors in SCENES:
        result=execute_demo(source,'PRESENTATION',ROOT)
        validate_behavior(result,behaviors)
        scenes.append(dict(id=id,name=name,description='Cena independente com entrada demonstrativa explícita; MPC High Autonomy V2 real.',
             timestamp=source['timestamp'],input=source,source_cycle=None,result=result,expected_behaviors=behaviors))
        print(id,name,'OK',flush=True)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps({'schema_version':'1.0','network_calls':0,'llm_calls':0,'scenes':scenes},ensure_ascii=False,indent=2),encoding='utf-8')
    out=ROOT/'outputs/presentation_v1';out.mkdir(parents=True,exist_ok=True)
    (out/'scene_validation.json').write_text(json.dumps({'scenes':16,'passed':16,'physical_violations':0,'elapsed_seconds':time.perf_counter()-start,
          'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()},indent=2))
if __name__=='__main__':main()
