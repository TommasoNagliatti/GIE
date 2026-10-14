"""Own only the children created here. No install, data cleanup, or port killing."""
import json,os,secrets,socket,subprocess,sys,time,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
IDS=['Commercial_HighAutonomy_V2','DEMO_POSTO_24H_001','DEMO_CASA_001','NEW_NO_HISTORY']

def main():
    core=Path(os.environ.get('GIE_CORE_PYTHON',str(ROOT/'.venv/Scripts/python.exe')))
    ui=Path(os.environ.get('GIE_DEMO_PYTHON',str(ROOT/'.venv-demo/Scripts/python.exe')))
    for exe in (core,ui):
        if not exe.is_file():raise RuntimeError('Configure GIE_CORE_PYTHON e GIE_DEMO_PYTHON para seus ambientes Python existentes.')
    for port in (8520,8504):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))==0:raise RuntimeError(f'Porta {port} ocupada. Nenhum processo foi encerrado.')
    runtime=ROOT/'reports/panel/v1/runtime';runtime.mkdir(parents=True,exist_ok=True)
    token=secrets.token_urlsafe(36)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT/'src')+os.pathsep+str(ROOT/'src/gie_multistation/.deps'),GIE_PANEL_TOKEN=token,GIE_MULTISTATION_TOKENS=json.dumps({token:IDS}),GIE_PANEL_RUNTIME=str(runtime))
    original=ROOT
    jobs=[('api',ROOT,[str(core),'-B','-m','gie_panel.server']),('panel',ROOT,[str(ui),'-B','-m','streamlit','run',str(ROOT/'src/gie_panel/app.py'),'--server.address=127.0.0.1','--server.port=8504','--server.headless=true','--theme.base=dark']),('original',original,[str(ui),'-B','-m','streamlit','run','demo/high_autonomy_v2/app.py','--server.address=127.0.0.1','--server.port=8503','--server.headless=true'])]
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8503))==0:
            jobs=jobs[:2]
            print('Porta 8503 já ocupada: painel existente preservado; não será iniciado nem encerrado por este launcher.',flush=True)
    processes=[];logs=[]
    try:
        for name,cwd,cmd in jobs:
            log=open(runtime/(name+'.log'),'a',encoding='utf-8');logs.append(log)
            child_env=dict(env)
            if name=='original':child_env['PYTHONPATH']=str(original/'src')
            p=subprocess.Popen(cmd,cwd=cwd,env=child_env,stdout=log,stderr=subprocess.STDOUT);processes.append(p)
        (runtime/'processes.json').write_text(json.dumps(dict(launcher=os.getpid(),children=[p.pid for p in processes])),encoding='utf-8')
        from urllib.request import Request,urlopen
        for attempt in range(60):
            if any(p.poll() is not None for p in processes):raise RuntimeError('Um serviço encerrou; consulte os logs locais em reports/panel/v1/runtime.')
            try:
                with urlopen(Request('http://127.0.0.1:8520/v1/health',headers={'Authorization':'Bearer '+token}),timeout=2):pass
                with urlopen('http://127.0.0.1:8504/_stcore/health',timeout=2):pass
                break
            except OSError:time.sleep(1)
        else:raise RuntimeError('Serviços não ficaram prontos no prazo.')
        print('Painel: http://127.0.0.1:8504 | Original: http://127.0.0.1:8503\nMantenha esta janela aberta. Ctrl+C encerra somente estes serviços.',flush=True)
        if '--no-browser' not in sys.argv:webbrowser.open('http://127.0.0.1:8504')
        while all(p.poll() is None for p in processes):time.sleep(1)
    except KeyboardInterrupt:pass
    finally:
        for p in reversed(processes):
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill()
        for log in logs:log.close()
if __name__=='__main__':main()
