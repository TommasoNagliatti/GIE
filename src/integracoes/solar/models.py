from dataclasses import dataclass, field
import pandas as pd

@dataclass
class SolarForecast:
    data: pd.DataFrame
    source: str
    stale: bool
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        records=[]
        for t,r in self.data.to_dict('index').items():
            records.append(dict(timestamp=t.isoformat(),**{k:None if pd.isna(v) else float(v) for k,v in r.items()}))
        return dict(source=self.source,stale=self.stale,metadata=self.metadata,records=records)
