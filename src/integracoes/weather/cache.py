"""Atomic provider-independent last-valid forecast cache, keyed by site."""
from pathlib import Path
import json, os, tempfile
import pandas as pd
from .models import WeatherBatch, COLUMNS, ZONE

class ForecastCache:
    def __init__(self,path):
        self.path=Path(path)

    def save(self,batch,key):
        batch.validate()
        payload=dict(version=1,key=key,fetched_at=batch.fetched_at.isoformat(),metadata=batch.metadata,
                     records=[dict(timestamp=t.isoformat(),**r) for t,r in batch.data[COLUMNS].to_dict('index').items()])
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=None
        try:
            with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=self.path.parent,suffix='.tmp',delete=False) as f:
                tmp=f.name;json.dump(payload,f,ensure_ascii=False,allow_nan=False)
            os.replace(tmp,self.path)
        finally:
            if tmp and os.path.exists(tmp):os.unlink(tmp)

    def load(self,key,now,max_age_hours):
        d=json.loads(self.path.read_text(encoding='utf-8'))
        if d['version']!=1 or d['key']!=key:
            raise ValueError('Cache configuration mismatch.')
        fetched=pd.Timestamp(d['fetched_at'])
        if fetched.tzinfo is None or not 0 <= (now-fetched).total_seconds() <= max_age_hours*3600:
            raise ValueError('Expired cache or invalid clock.')
        frame=pd.DataFrame(d['records'])
        ix=pd.to_datetime(frame.pop('timestamp'),utc=True).dt.tz_convert(ZONE)
        frame.index=pd.DatetimeIndex(ix)
        return WeatherBatch(frame,fetched,d['metadata']).validate()
