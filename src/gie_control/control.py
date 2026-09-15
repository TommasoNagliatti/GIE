"""Per-instance control; presentation is pull-driven, bounded and offline."""
from copy import deepcopy
import json,time
from .engine import GIEEngine
from .profile import ROOT
from .outputs import MODES
from .scenarios import execute_demo,apply_event,EVENTS
from load_balancer.state import BalancerState

class GIEControl:
    def __init__(self,engine=None,scenes=None,clock=None,demo_runner=None):
        self.engine=engine or GIEEngine()
        self.demo_runner=demo_runner or execute_demo
        if scenes is None:
            scenes=json.loads((ROOT/'src/gie_control/assets/scenes.json').read_text(encoding='utf-8'))['scenes']
        self.scenes=deepcopy(scenes)
        if len(self.scenes)!=16 or len({s['id'] for s in self.scenes})!=16:raise ValueError('16 unique scenes required')
        self.clock=clock or time.monotonic;self.mode='NORMAL';self.index=0
        self.playing=False;self.interval=10;self.loop=False;self.due=None;self.remaining=10
        self.result=None;self.message_history=[];self.demo_input=deepcopy(self.scenes[4]['input']);self.demo_previous=None

    def _store(self,result):
        self.result=deepcopy(result)
        self.message_history.append({'timestamp':result['timestamp'],'mode':self.mode,'message':deepcopy(result['primary_message'])})
        self.message_history=self.message_history[-100:]
        return self.get_state()

    def get_state(self):return deepcopy(self.result)
    def get_mode(self):return self.mode
    def set_mode(self,mode):
        if mode not in MODES:raise ValueError('Unknown mode')
        self.pause_presentation();self.mode=mode;self.result=None
        if mode=='PRESENTATION':self._scene()
        return self.get_mode()
    def run_cycle(self,*args,**kwargs):
        if self.mode not in ('NORMAL','SIMULATION'):raise ValueError('Current mode does not accept normal telemetry')
        return self._store(self.engine.run_cycle(*args,mode=self.mode,**kwargs))
    def _scene(self):
        r=deepcopy(self.scenes[self.index]['result']);r['mode']='PRESENTATION'
        return self._store(r)
    def start_presentation(self):
        if self.mode!='PRESENTATION':self.set_mode('PRESENTATION')
        self.playing=True;self.due=self.clock()+self.interval;self.remaining=self.interval
        if self.result is None:self._scene()
        return self.get_presentation_state()
    def pause_presentation(self):
        if self.playing:self.remaining=max(0.,self.due-self.clock())
        self.playing=False;self.due=None
    def resume_presentation(self):
        if self.mode!='PRESENTATION':raise ValueError('Not in presentation mode')
        self.playing=True;self.due=self.clock()+self.remaining
    def stop_presentation(self):
        self.pause_presentation();self.index=0;self.remaining=self.interval
        if self.mode=='PRESENTATION':self._scene()
    def _require_presentation(self):
        if self.mode!='PRESENTATION':raise ValueError('Not in presentation mode')
    def set_scene(self,scene_id):
        self._require_presentation()
        ids=[s['id'] for s in self.scenes]
        if scene_id not in ids:raise ValueError('Unknown scene')
        self.index=ids.index(scene_id);self.remaining=self.interval
        if self.playing:self.due=self.clock()+self.interval
        return self._scene()
    def next_scene(self):
        self._require_presentation()
        if self.index==15:
            if self.loop:self.index=0
            else:self.pause_presentation();return self.get_state()
        else:self.index+=1
        self.remaining=self.interval
        if self.playing:self.due=self.clock()+self.interval
        return self._scene()
    def previous_scene(self):return self.set_scene(self.scenes[max(0,self.index-1)]['id'])
    def set_presentation_interval(self,seconds):
        if seconds not in (5,10,15):raise ValueError('Interval must be 5, 10 or 15 seconds')
        self.interval=seconds;self.remaining=seconds
        if self.playing:self.due=self.clock()+seconds
    def set_loop(self,enabled):
        if type(enabled) is not bool:raise ValueError('Loop must be bool')
        self.loop=enabled
    def tick(self):
        if self.mode=='PRESENTATION' and self.playing and self.clock()>=self.due:
            self.next_scene() # never catch up an uncontrolled backlog
        return self.get_state()
    def get_presentation_state(self):
        s=self.scenes[self.index]
        return dict(scene_id=s['id'],scene_number=self.index+1,scene_count=16,name=s['name'],
                    playing=self.playing,interval_seconds=self.interval,loop=self.loop,mode=self.mode)
    def trigger_demo_event(self,event_code):
        if self.mode!='MANUAL_DEMO':raise ValueError('Events only allowed in MANUAL_DEMO')
        self.demo_input=apply_event(self.demo_input,event_code)
        result=self.demo_runner(self.demo_input,root=self.engine.root,previous=self.demo_previous)
        if result['execution_allowed']:self.demo_previous=BalancerState(**result['load_balancer']['next_state'])
        return self._store(result)
    def reset_demo(self):
        if self.mode!='MANUAL_DEMO':raise ValueError('Not in manual demo')
        self.demo_input=deepcopy(self.scenes[4]['input']);self.demo_previous=None
        return self._store(self.demo_runner(self.demo_input,root=self.engine.root))
