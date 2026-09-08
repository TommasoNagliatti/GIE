"""UI-independent, offline replay state and bounded playback."""
from pathlib import Path
from copy import deepcopy
import json

class ReplaySession:
    def __init__(self,path):
        self.path=Path(path)
        self.frames=[json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if not self.frames:raise ValueError('Empty replay.')
        self.index=0;self.playing=False;self.last_advance=None
    def current(self):return deepcopy(self.frames[self.index])
    def advance(self,now,automatic=False,delay=8):
        if automatic and (not self.playing or (self.last_advance is not None and now-self.last_advance<max(3,delay))):return False
        if self.index>=len(self.frames)-1:self.playing=False;return False
        self.index+=1;self.last_advance=now
        if self.index==len(self.frames)-1:self.playing=False
        return True
    def reset(self):self.index=0;self.playing=False;self.last_advance=None

class LiveGate:
    def __init__(self):self.last_request=None;self.busy=False;self.count=0
    def begin(self,now):
        if self.busy or (self.last_request is not None and now-self.last_request<30):return False
        self.busy=True;self.last_request=now;self.count+=1;return True
    def end(self):self.busy=False
