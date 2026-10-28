"""Media screens are protected unless a bounded explicit watch plan is active."""
import math
import random
import time
import threading
from PySide6.QtCore import QObject,Signal
from .media_windows import scan_media
from .model import LocalModel

def screen_key(area):
    return f'{area.x},{area.y}'

class MediaGuard:
    def __init__(self):
        self.detected={}
        self.manual=set()
        self.watching=None

    def update(self,records,areas):
        detected={}
        if areas:
            for item in records:
                origin=item['origin']
                area=min(areas,key=lambda a:math.dist((a.x,a.y),origin))
                detected[screen_key(area)]=dict(item,screen=screen_key(area))
        self.detected=detected

    def protected(self):return set(self.detected)|self.manual

    def allowed(self,areas):
        protected=self.protected()
        return [a for a in areas if screen_key(a) not in protected]

    def watch_perch(self,key,areas,size,rng):
        area=next((a for a in areas if screen_key(a)==key),None)
        if area is None:raise ValueError('Media screen disconnected')
        left=rng.choice([True,False])
        x=area.x+12 if left else area.x+area.width-size[0]-12
        y=area.y+(area.height-size[1])//2
        point=area.clamp((x,y),size)
        return tuple(map(round,point)),('watch-right' if left else 'watch-left')

class MediaController(QObject):
    changed=Signal()
    watch_started=Signal(str,object)
    watch_stopped=Signal(str)
    status=Signal(str)
    _scan_done=Signal(object)
    _decision_done=Signal(object)
    _decision_failed=Signal()

    def __init__(self,config,guard,areas_provider,personality_provider):
        super().__init__()
        self.config,self.guard=config,guard
        self.areas_provider,self.personality_provider=areas_provider,personality_provider
        self._scan_done.connect(self.apply_scan)
        self._decision_done.connect(self.apply_decision)
        self._decision_failed.connect(self.failed)
        self._scanning=self._deciding=False
        self._next_scan=0.
        self._next_decision=time.monotonic()+30
        self._watch_until=0.
        self._rng=random.Random()
        self._chat_busy=False

    def tick(self,chat_busy=False):
        now=time.monotonic()
        self._chat_busy=chat_busy
        if not self.config['media_avoidance']:
            if self.guard.watching:self.stop('Media avoidance turned off')
            self.guard.detected={};self.guard.manual=set();self.changed.emit()
            return
        self.guard.manual=set(self.config['protected_media_screens'])
        if not self._scanning and now>=self._next_scan:
            self._scanning=True;self._next_scan=now+3
            def work():
                try:result=scan_media()
                except Exception as error:result={'detected':None,'error':type(error).__name__}
                self._scan_done.emit(result)
            threading.Thread(target=work,name='capri-media-observer',daemon=True).start()
        if self.guard.watching:
            if not self.config['automatic_media_watch']:
                self.stop('Automatic watching turned off')
            elif (self.guard.watching not in self.guard.detected
                  or self.guard.watching not in {screen_key(a) for a in self.areas_provider()}
                  or now>=self._watch_until):
                self.stop('Finished watching' if now>=self._watch_until else 'Playback stopped')
            return
        if not self.config['automatic_media_watch'] or chat_busy or self._deciding or now<self._next_decision or not self.guard.detected:return
        self._next_decision=now+60
        profile=self.personality_provider()
        if self._rng.random()>.1+.25*profile.curiosity:return
        key=self._rng.choice(list(self.guard.detected))
        candidate=dict(self.guard.detected[key])
        self._deciding=True
        def decide():
            try:
                result=LocalModel(self.config).media_choice(candidate,profile.as_dict())
                result['screen']=key
                result['candidate']=(candidate.get('app'),candidate.get('media_title',candidate.get('title')))
                self._decision_done.emit(result)
            except Exception:self._decision_failed.emit()
        threading.Thread(target=decide,name='capri-watch-decision',daemon=True).start()

    def apply_scan(self,result):
        self._scanning=False
        if not self.config['media_avoidance']:return
        if result.get('detected') is not None:
            previous=dict(self.guard.detected)
            # If session access temporarily fails, retain known media screens;
            # fullscreen detections still add protection until access recovers.
            self.guard.update(result['detected'],self.areas_provider())
            if result.get('error'):self.guard.detected={**previous,**self.guard.detected}
            self.changed.emit()
        if result.get('error'):
            self.status.emit('Media sessions unavailable; fullscreen/manual protection remains active')
        elif self.guard.watching:
            self.status.emit('Capri is watching with popcorn')
        else:self.status.emit(f'{len(self.guard.protected())} media screen(s) protected')

    def apply_decision(self,result):
        self._deciding=False
        key=result.get('screen')
        if not self.config['automatic_media_watch'] or not self.config['media_avoidance'] or key not in self.guard.detected:return
        current=self.guard.detected[key]
        fingerprint=(current.get('app'),current.get('media_title',current.get('title')))
        if result.get('candidate') is not None and tuple(result['candidate'])!=fingerprint:return
        if self._chat_busy:
            self._next_decision=time.monotonic()+60
            return
        if result.get('action')=='watch':
            seconds=max(30,min(180,int(result.get('seconds',60))))
            self.guard.watching=key
            self._watch_until=time.monotonic()+seconds
            self.watch_started.emit(key,result)
            self.status.emit('Chose to watch: '+str(result.get('reason','Curious about the media'))[:100])
        else:
            self._next_decision=time.monotonic()+180
            self.status.emit('Capri chose to stay out of the media screen')

    def failed(self):
        self._deciding=False
        self._next_decision=time.monotonic()+180
        self.status.emit('Watch decision unavailable; staying out of media screens')

    def stop(self,reason='Stopped watching'):
        if self.guard.watching:
            self.guard.watching=None
            self._next_decision=time.monotonic()+600
            self.watch_stopped.emit(reason)
            self.changed.emit()
