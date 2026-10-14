"""Immutable, validated local registrations. No API-supplied filesystem paths."""
import hashlib,json,os
from pathlib import Path
from .contracts import Provision

def packed(data):return json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False)
def load(directory):
    result={};folder=Path(directory)/'configurations'
    if not folder.exists():return result
    for path in sorted(folder.glob('*.json')):
        record=json.loads(path.read_text(encoding='utf-8'));technical=Provision.model_validate(record['technical'])
        if path.stem!=technical.station_id or record['sha256']!=hashlib.sha256(packed(technical.model_dump()).encode()).hexdigest():raise ValueError('Registration integrity mismatch')
        result[technical.station_id]=technical.worker_config()
    return result

def save(directory,technical):
    folder=Path(directory)/'configurations';folder.mkdir(exist_ok=True)
    path=folder/(technical.station_id+'.json')
    raw=technical.model_dump();record=dict(technical=raw,sha256=hashlib.sha256(packed(raw).encode()).hexdigest())
    # Single manager owns this directory. No replacement of approved registrations.
    temp=path.with_suffix('.pending')
    with temp.open('x',encoding='utf-8') as f:
        json.dump(record,f,allow_nan=False);f.flush();os.fsync(f.fileno())
    if path.exists():raise ValueError('Registration already exists')
    temp.rename(path)
    return technical.worker_config()
