"""Append-only JSONL audit log. Use one file per writer/session."""
import json,os,threading
from pathlib import Path

class DecisionLog:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock();self.seen=set()
        if self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                if line.strip():self.seen.add(json.loads(line)['trace_id'])
    def append(self,trace):
        with self.lock:
            if trace['trace_id'] in self.seen:return 0
            records=[]
            for d in trace['decisions']:
                records.append(dict(timestamp=d['timestamp'],code='DECISION_CHANGED' if d['changed'] else 'DECISION_OBSERVED',severity='info',component=d['component'],
                    previous_value=d['previous_value'],new_value=d['new_value'],reason_codes=d['reason_codes'],context={'action':d['action'],**d['context']},record_kind='decision'))
            records.extend(dict(e,record_kind='event') for e in trace['events'])
            for r in records:r['trace_id']=trace['trace_id']
            payload=''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+chr(10) for r in records)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.path.open('a',encoding='utf-8',newline=chr(10)) as f:
                f.write(payload);f.flush();os.fsync(f.fileno())
            self.seen.add(trace['trace_id'])
            return len(records)
