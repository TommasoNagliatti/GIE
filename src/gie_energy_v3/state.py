"""Atomic simulated state. No physical telemetry, command replay or silent reset."""
import json,os
from pathlib import Path
import pandas as pd

class SimulatedState:
    def __init__(self,c,path=None):
        self.c=c;self.path=Path(path) if path else None;self.energy=c.initial_energy();self.last_issue=None;self.cycles=0
        if self.path and self.path.exists():
            d=json.loads(self.path.read_text(encoding='utf-8'))
            if d['station_id']!=c.station_id or d['configuration_sha256']!=c.fingerprint() or d['origin']!='SIMULATED':raise ValueError('Checkpoint identity/configuration mismatch; no automatic reset')
            self.energy=d['energy_kwh'];self.last_issue=pd.Timestamp(d['last_issue']);self.cycles=d['cycles']
            if self.last_issue.tzinfo is None:raise ValueError('Checkpoint timezone missing')
            if set(self.energy)!={b.battery_id for b in c.batteries}:raise ValueError('Checkpoint battery identities mismatch')
            for b in c.batteries:
                e=self.energy[b.battery_id]
                if not b.soc_min*b.capacity_kwh-1e-6<=e<=b.soc_max*b.capacity_kwh+1e-6:raise ValueError('Checkpoint SOC invalid')
    def view(self):
        return dict(origin='SIMULATED',station_id=self.c.station_id,configuration_sha256=self.c.fingerprint(),energy_kwh=dict(self.energy),last_issue=self.last_issue.isoformat() if self.last_issue is not None else None,cycles=self.cycles)
    def commit(self,issue,first):
        new={b.battery_id:first['batteries'][b.battery_id]['energy_after_kwh'] for b in self.c.batteries}
        payload=dict(origin='SIMULATED',station_id=self.c.station_id,configuration_sha256=self.c.fingerprint(),energy_kwh=new,last_issue=issue.isoformat(),cycles=self.cycles+1)
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
            with temp.open('w',encoding='utf-8') as f:json.dump(payload,f,allow_nan=False);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.path)
        self.energy=new;self.last_issue=issue;self.cycles+=1
