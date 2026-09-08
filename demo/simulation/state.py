"""Wall clock controls, independent from simulation physics and Streamlit."""
from dataclasses import dataclass
from datetime import datetime,timedelta
SPEEDS={"1 min real = 15 min simulados":60.0,"1 min real = 1 h simulada":15.0,"1 min real = 2 h simuladas":7.5}
@dataclass
class Playback:
    interval:float=15.
    playing:bool=False
    next_due:float|None=None
    def start(self,now):self.playing=True;self.next_due=now
    def pause(self):self.playing=False;self.next_due=None
    def due(self,now):return self.playing and self.next_due is not None and now>=self.next_due
    def completed(self,started,finished):self.next_due=max(started+self.interval,finished+0.1) if self.playing else None
    def speed(self,interval,now):
        if interval not in SPEEDS.values():raise ValueError("Unsupported speed")
        fraction=max(0,(self.next_due-now)/self.interval) if self.next_due is not None else 0
        self.interval=interval
        if self.playing:self.next_due=now+min(1,fraction)*interval
    def reset(self):self.pause()

def initial(start="2026-06-15 00:00:00",hours=24,soc=50):
    t=datetime.fromisoformat(str(start))
    if t.minute%15 or t.second or t.microsecond or t.tzinfo:raise ValueError("Use local aligned quarter-hour timestamp")
    if not isinstance(hours,int) or not 1<=hours<=48:raise ValueError("Duration must be 1–48 hours")
    if not 20<=soc<=95:raise ValueError("SOC outside prototype limits")
    return dict(version="1.0",start=t.isoformat(),hours=hours,total_steps=hours*4,index=0,soc=soc,initial_soc=soc,
                previous_charge_kw=0.,previous_discharge_kw=0.,balancer_state=None,connected_since={},observations=[],previous_trace=None,events=[],last_frame=None,rows=[],stopped=False)
def timestamp(state):return datetime.fromisoformat(state["start"])+timedelta(minutes=15*state["index"])
