"""UI transport only. No optimization or station state lives in this module."""
import json,os
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from urllib.parse import urlparse

class APIError(RuntimeError):pass

class Client:
    def __init__(self):
        self.base=os.environ.get('GIE_PANEL_API','http://127.0.0.1:8520').rstrip('/')
        if urlparse(self.base).hostname not in ('localhost','127.0.0.1'):raise APIError('API deve ser local')
        self.token=os.environ.get('GIE_PANEL_TOKEN','')
    def call(self,path,body=None):
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=100) as r:return json.load(r)
        except HTTPError as exc:
            try:detail=json.load(exc).get('detail','Falha na API')
            except ValueError:detail='Falha na API'
            raise APIError(str(detail)) from exc
        except (URLError,TimeoutError,OSError) as exc:
            raise APIError('Sem comunicação com a API. Nenhuma decisão anterior é apresentada como atual.') from exc
