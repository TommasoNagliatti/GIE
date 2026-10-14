"""Trusted local registry. API callers cannot choose paths, profiles or model IDs."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name('stations.json')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def registry():
    records = json.loads(REGISTRY.read_text(encoding='utf-8'))['stations']
    result = {}
    for c in records:
        sid = c['station_id']
        if sid in result or not sid.replace('_', '').isalnum():
            raise ValueError('Invalid station registry')
        path = (ROOT / c['profile_path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != c['profile_sha256']:
            raise ValueError('Profile integrity mismatch')
        if c['kind'] == 'forecast':
            folder = (ROOT / c['model_path']).resolve()
            if not folder.is_relative_to(ROOT) or digest(folder / 'freeze.json') != c['model_freeze_sha256']:
                raise ValueError('Model registry integrity mismatch')
        for name, expected in c.get('artifact_sha256', {}).items():
            artifact = (ROOT / name).resolve()
            if not artifact.is_relative_to(ROOT) or digest(artifact) != expected:
                raise ValueError('Commercial artifact integrity mismatch')
        result[sid] = c
    return result
