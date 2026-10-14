"""Real HTTP demo with three spawned model workers; no credentials are saved."""
import concurrent.futures as cf
import json
from pathlib import Path
import secrets
import socket
import tempfile
import threading
import time
import httpx
import uvicorn
from .api import create_app
from .registry import ROOT,registry

def main():
    stations=list(registry());token=secrets.token_urlsafe(32)
    records=[]
    with tempfile.TemporaryDirectory(prefix='gie-http-demo-') as directory:
        app=create_app({token:stations},directory)
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
        port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='warning'))
        thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
        try:
            deadline=time.monotonic()+20
            while not server.started:
                if time.monotonic()>deadline:raise RuntimeError('HTTP startup failed')
                time.sleep(.05)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',headers={'Authorization':'Bearer '+token},timeout=120) as client:
                def request(method,path,body=None):
                    r=client.request(method,path,json=body)
                    records.append({'method':method,'path':path,'status':r.status_code})
                    r.raise_for_status();return r.json()
                request('GET','/v1/health');request('GET','/v1/stations')
                with cf.ThreadPoolExecutor(3) as pool:
                    initial=list(pool.map(lambda s:request('POST',f'/v1/stations/{s}/initialize',{}),stations))
                with cf.ThreadPoolExecutor(3) as pool:
                    states=list(pool.map(lambda s:request('POST',f'/v1/stations/{s}/cycle',{}),stations))
                assert len({s['pid'] for s in states})==3
                summaries=[]
                for s in states:
                    out=s['state'];sid=s['station_id']
                    request('GET',f'/v1/stations/{sid}/state');request('GET',f'/v1/stations/{sid}/health')
                    summaries.append({k:s[k] for k in ['station_id','pid','generation','model_identity','capabilities','history']})
                    summaries[-1].update(status=out['status'],forecast_steps=len(out['forecasts']['records']),numeric_state=out['numeric_state'],source=s['source'],hardware_commands_sent=False)
                comm=stations[0]
                request('POST',f'/v1/stations/{comm}/mode',{'mode':'PRESENTATION'})
                for action in ['start','pause','next','reset']:
                    request('POST',f'/v1/stations/{comm}/presentation',{'action':action})
                for sid in stations:
                    request('POST',f'/v1/stations/{sid}/stop',{})
                output={'transport':'real loopback HTTP','port':port,'station_count':3,'requests':records,'stations':summaries,'service_stopped_after_demo':True}
                (ROOT/'reports/multistation/v1/http_demo.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
                print('HTTP demo:',len(records),'requests; 3 independent model processes; no hardware commands')
        finally:
            server.should_exit=True;thread.join(20);listener.close()
            if thread.is_alive():raise RuntimeError('HTTP server did not stop cleanly')

if __name__=='__main__':main()
