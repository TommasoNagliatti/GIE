"""Reproduce new datasets only. Never touches original data/models/core."""
import argparse,os,subprocess,urllib.request,zipfile
from pathlib import Path
from loads import ROOT,PROFILES,prepare
from generate import generate,sha,save_json,comparison

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--openstudio',default=os.environ.get('OPENSTUDIO_EXE','openstudio'))
    parser.add_argument('--energyplus',default=os.environ.get('ENERGYPLUS_EXE','energyplus'))
    args=parser.parse_args()
    import json
    src=json.loads((ROOT/'weather/source.json').read_text(encoding='utf-8-sig'))
    archive=ROOT/'weather/source.zip'
    if not archive.exists():archive.write_bytes(urllib.request.urlopen(src['url'],timeout=90).read())
    if sha(archive)!=src['sha256']:raise RuntimeError('Weather archive hash changed; review source, do not silently replace')
    with zipfile.ZipFile(archive) as z:
        for n in z.namelist():
            if n.lower().endswith(('.epw','.ddy','.stat')):(ROOT/'weather'/Path(n).name).write_bytes(z.read(n))
    epw=next((ROOT/'weather').glob('*.epw'))
    curves={}
    for profile in PROFILES:
        directory=prepare(profile)
        result=subprocess.run([args.openstudio,str(ROOT/'build_model.rb'),profile],cwd=directory,capture_output=True,text=True)
        (directory/'model_build.txt').write_text(result.stdout+result.stderr,encoding='utf-8');result.check_returncode()
        result=subprocess.run([args.energyplus,'-w',str(epw),'-d',str(directory/'run'),str(directory/'building.idf')],cwd=directory,capture_output=True,text=True)
        (directory/'energyplus_execution.txt').write_text(result.stdout+result.stderr,encoding='utf-8');result.check_returncode()
        curves[profile]=generate(profile)
    comparison(curves)
    subprocess.run([os.sys.executable,'-B',str(ROOT/'validate.py'),'--energyplus',args.energyplus],check=True)

if __name__=='__main__':main()
