"""Play a sprite loop in place; decompile/zip/recompile when the loop changes."""
from dataclasses import dataclass
import json
import math
import random
import time
from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget
from .config import PROJECT
from .animation import frame_index, timed_frame_index
from .behavior import BehaviorEngine, CursorTracker
from .interactions import PointerReactions
from .media import screen_key
from .motion import Area, destination, nearest_visible, transition_phase

@dataclass
class SpriteLoop:
    name: str
    fps: float
    frames: list
    durations_ms: tuple = ()
    playback: str = 'loop'

    @property
    def duration(self):
        return sum(self.durations_ms)/1000 if self.durations_ms else len(self.frames)/self.fps

    def index(self, elapsed, repeat=True):
        if self.durations_ms:
            return timed_frame_index(elapsed,self.durations_ms,repeat)
        return frame_index(elapsed,self.fps,len(self.frames))

class DesktopPet(QWidget):
    chat_requested = Signal()
    memory_requested = Signal()
    quit_requested = Signal()
    config_changed = Signal()
    stop_watching_requested = Signal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(config['size'] + 90, config['size'] + 110)
        self.state = 'idle'
        self._logical_state = 'idle'
        self._pending = None
        self._transition = None
        self._drag = None
        self._pressed = None
        self._last_interaction = time.monotonic()
        self._bubble = ''
        self._bubble_until = 0
        self._pause_until = 0
        self.behavior = None
        self._neutral_behavior = BehaviorEngine()
        self.cursor = CursorTracker()
        self.interactions = PointerReactions()
        self._hit_image = None
        self._hit_key = None
        self._drag_moved = False
        self.media_guard = None
        self.watching = None
        self._sense_next = 0.
        self._rng = random.Random()
        self._switch_next = time.monotonic() + self.switch_delay()
        folder = PROJECT / 'assets' / 'companion'
        spec = json.loads((folder / 'animations.json').read_text())
        def load(item):
            loop=SpriteLoop(item['name'],float(item['fps']),
                [QPixmap(str(folder/p)) for p in item['frames']],
                tuple(item.get('durations_ms',())),item.get('playback','loop'))
            if loop.durations_ms:
                if len(loop.durations_ms)!=len(loop.frames):raise ValueError('Frame timing count mismatch')
                timed_frame_index(0,loop.durations_ms)
            return loop
        self.loops = {state:[load(item) for item in items] for state,items in spec.items()}
        transition_file=folder/'transitions.json'
        self.transition_loops=({direction:load(item) for direction,item in
            json.loads(transition_file.read_text()).items()} if transition_file.exists() else {})
        if any(len(loop.frames) < 2 or loop.fps <= 0 or any(p.isNull() for p in loop.frames)
               for loops in [*self.loops.values(),list(self.transition_loops.values())] for loop in loops):
            raise RuntimeError('An animation loop has missing frames or invalid timing')
        self.loop = self.loops['idle'][0]
        self._loop_started = time.monotonic()
        self._frame_index = 0
        self.pose = self.loop.frames[0]
        self._target_loop = self.loop
        self._next_pose = self.pose
        self._pieces = []
        screens = QApplication.screens()
        for screen in screens:
            self.watch_screen(screen)
        QApplication.instance().screenAdded.connect(self.watch_screen)
        QApplication.instance().screenRemoved.connect(lambda *_: self.ensure_visible())
        initial = self.areas()[0]
        self.move(*initial.clamp((initial.x + initial.width - self.width() - 40,
                                 initial.y + initial.height - self.height()), self.dimensions()))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    def dimensions(self):
        return self.width(), self.height()

    def areas(self):
        return [Area(r.x(), r.y(), r.width(), r.height())
                for r in [s.availableGeometry() for s in QApplication.screens()]]

    def travel_areas(self):
        areas=self.areas()
        if self.media_guard is None or not self.config['media_avoidance']:return areas
        safe=self.media_guard.allowed(areas)
        if self.watching:
            safe += [a for a in areas if screen_key(a)==self.watching['screen'] and a not in safe]
        return safe

    def base_state(self):
        return self.watching['loop'] if self.watching else self._logical_state

    def start_watching(self,screen):
        target,loop=self.media_guard.watch_perch(screen,self.areas(),self.dimensions(),self._rng)
        self.watching={'screen':screen,'loop':loop}
        self.interactions.update(False,time.monotonic(),False)
        self._transition=self._pending=None
        self.show()
        self.morph(loop,target=target)

    def stop_watching(self):
        self.watching=None
        self._transition=self._pending=None
        self.interactions.update(False,time.monotonic(),False)
        safe=self.travel_areas()
        if safe:
            target=destination(safe,self.dimensions(),self._rng)
            self.morph(self._logical_state,target=target)
        else:
            self._target_loop=self.pick_loop(self._logical_state)
            self.commit_loop(time.monotonic(),self._logical_state)
            self.hide()

    def enforce_media(self):
        safe=self.travel_areas()
        if not safe:
            self.hide()
            return
        self.show()
        point=(self.x(),self.y())
        if not any(a.contains(point,self.dimensions()) for a in safe):
            self.interactions.update(False,time.monotonic(),False)
            self._transition=self._pending=None
            self.morph(self.base_state(),target=nearest_visible(point,self.dimensions(),safe))

    def protect_screen(self,index,enabled):
        keys=set(self.config['protected_media_screens'])
        key=screen_key(self.areas()[index])
        if enabled:keys.add(key)
        else:keys.discard(key)
        self.config.set('protected_media_screens',sorted(keys))
        if self.media_guard:
            self.media_guard.manual=keys
            self.enforce_media()

    def watch_screen(self, screen):
        screen.availableGeometryChanged.connect(lambda *_: self.ensure_visible())
        self.ensure_visible()

    def ensure_visible(self):
        legal=self.travel_areas()
        if legal:
            self.move(*nearest_visible((self.x(), self.y()), self.dimensions(), legal))
        elif self.areas():
            self.hide()

    def switch_delay(self):
        low = max(1., float(self.config['loop_min_seconds']))
        high = max(low, float(self.config['loop_max_seconds']))
        if self.behavior is not None and self.config['personality_behavior']:
            return self.behavior.switch_delay(low, high, self._rng)
        return self._rng.uniform(low, high)

    def pick_loop(self, state):
        choices = self.loops.get(state, self.loops['idle'])
        alternatives = [loop for loop in choices if loop.name != self.loop.name]
        if self.behavior is not None and self.config['personality_behavior']:
            return self.behavior.choose_loop(alternatives or choices, self._rng, self.cursor.observation(time.monotonic()))
        return self._rng.choice(alternatives or choices)

    def sample_cursor(self, now, force=False):
        if not self.config['mouse_awareness']:
            self.cursor.disable()
            return
        if not force and now < self._sense_next:
            return
        self._sense_next = now + .1
        point = QCursor.pos()
        screen = QApplication.screenAt(point)
        screens = QApplication.screens()
        rect = (self.x() + 45, self.y() + 80, self.config['size'], round(self.config['size'] * 208 / 192))
        self.cursor.sample((point.x(), point.y()), screen.name() if screen else '',
                           screens.index(screen) + 1 if screen in screens else None, rect, now,
                           over_sprite=self.hit_sprite((point.x(),point.y())))

    def hit_sprite(self, point):
        scale = self.config['size'] / 192
        x = math.floor((point[0] - self.x() - 45) / scale)
        y = math.floor((point[1] - self.y() - 80) / scale)
        if not (0 <= x < 192 and 0 <= y < 208):
            return False
        if self._hit_key != self.pose.cacheKey():
            self._hit_key = self.pose.cacheKey()
            self._hit_image = self.pose.toImage()
        return self._hit_image.pixelColor(x,y).alpha() >= 90

    def play_reaction(self, kind):
        self._last_interaction = time.monotonic()
        self.morph(kind, target=(self.x(),self.y()))

    def poke(self):
        if not self.config['mouse_reactions']:
            return False
        now = time.monotonic()
        repeat = self.interactions.active == 'poke' and self.state == 'poke' and not self._transition
        duration = 2.2
        if self.behavior is not None and self.config['personality_behavior']:
            duration += .6 * self.behavior.profile.playfulness
        self.interactions.poke(now,duration)
        self._pause_until = now + duration + .5
        if repeat:
            self._loop_started = now
            self._frame_index = 0
            self.pose = self.loop.frames[0]
            self.update()
        else:
            self.play_reaction('poke')
        return True

    def observation(self):
        now = time.monotonic()
        self.sample_cursor(now, force=True)
        return {'source': 'desktop-controller', 'animation': self.loop.name, 'activity': self._logical_state,
                'capri_window_position': [self.x(), self.y()],
                'capri_screen': self.screen().name() if self.screen() else '',
                'changing_animation': self._transition is not None,
                'pointer_reaction': self.interactions.active,
                'last_poke_seconds_ago': (round(now-self.interactions.last_poke,1)
                                          if self.interactions.last_poke is not None else None),
                'watching_media':self.watching is not None,
                'protected_media_screens':len(self.media_guard.protected()) if self.media_guard else 0,
                'cursor': self.cursor.observation(now)}

    def advance_loop(self, now):
        # Desktop behavior intentionally repeats even the pack's suggested
        # one-shot expressions until its controller chooses another loop.
        index = self.loop.index(now-self._loop_started)
        if index != self._frame_index:
            self._frame_index = index
            self.pose = self.loop.frames[index]
            self.update()

    def commit_loop(self, now, state):
        self.loop = self._target_loop
        self._loop_started = now
        self._frame_index = 0
        self.pose = self.loop.frames[0]
        self.state = state
        self._switch_next = now + self.switch_delay()

    def set_state(self, state):
        if state == self._logical_state:
            return
        self._logical_state = state
        if self.interactions.active or self.watching:
            return
        if self._transition:
            self._pending = (state, None)
        else:
            self.morph(state)

    def say(self, text, seconds=5):
        if not self.config['quiet']:
            self._bubble = text[:90]
            self._bubble_until = time.monotonic() + seconds
            self.update()

    def morph(self, state=None, target=None, loop_name=None):
        if self._transition or self._drag is not None:
            if state:
                self._pending = (state, target)
            return
        state = state or self.base_state()
        self._target_loop = (next(loop for loop in self.loops[state] if loop.name == loop_name)
                             if loop_name else self.pick_loop(state))
        if self._target_loop.name == self.loop.name and target is None:
            # The same visual loop may serve two activity states; keep playing it.
            self.state = state
            self._switch_next = time.monotonic() + self.switch_delay()
            return
        self._next_pose = self._target_loop.frames[0]
        areas=self.travel_areas()
        if not areas:
            self.hide()
            return
        if target is None and self.config['roaming'] and time.monotonic() >= self._pause_until:
            if self.behavior is not None and self.config['personality_behavior']:
                target = self.behavior.choose_destination(areas, self.dimensions(), self._rng,
                                                          self.cursor.observation(time.monotonic()))
            else:
                target = destination(areas, self.dimensions(), self._rng)
        target=nearest_visible(target or (self.x(),self.y()),self.dimensions(),areas)
        duration = (self.behavior.transition_duration(self.config['transition_seconds'])
                    if self.behavior is not None and self.config['personality_behavior'] else self.config['transition_seconds'])
        if state in ('hover','poke') or self.state in ('hover','poke'):
            duration = .2
        self._transition = {'start': time.monotonic(), 'origin': (self.x(), self.y()),
                            'target': target or (self.x(), self.y()), 'state': state, 'duration': duration}
        direction='left' if target[0]<self.x() else 'right'
        self._transition['clip']=self.transition_loops.get(direction)
        # Fragments are samples of the actual sprite pixels, not a replacement drawing.
        self._pieces = []
        for y in range(0, 208, 16):
            for x in range(0, 192, 16):
                self._pieces.append((x, y, self._rng.uniform(-40, 40), self._rng.uniform(-40, 35), self._rng.random()))

    def teleport_to_screen(self, index):
        areas = self.areas()
        if areas[index] not in self.travel_areas():return
        self._pause_until = time.monotonic() + 5
        self.morph(target=destination(areas, self.dimensions(), self._rng, areas[index]))

    def motion_phase(self,progress):
        clip=self._transition.get('clip') if self._transition else None
        if not clip:return transition_phase(progress)
        # The authored middle two frames contain only the persistent eye box.
        # Relocate during those frames, then rebuild at the destination.
        total=sum(clip.durations_ms)
        begin=sum(clip.durations_ms[:3])/total
        end=sum(clip.durations_ms[:5])/total
        if progress<begin:return 'decompile',max(0.,progress/begin)
        if progress<end:return 'zip',(progress-begin)/(end-begin)
        return 'recompile',min(1.,(progress-end)/(1-end))

    def select_library_animation(self,state):
        if self.watching:self.stop_watching_requested.emit()
        self.interactions.update(False,time.monotonic(),False)
        self._transition=self._pending=None
        self._pause_until=time.monotonic()+8
        self.morph(state)

    def tick(self):
        now = time.monotonic()
        self.sample_cursor(now)
        if self._transition:
            t = self._transition
            progress = (now - t['start']) / t['duration']
            phase, part = self.motion_phase(progress)
            legal=self.travel_areas()
            if not legal:
                self.hide();return
            t['target']=nearest_visible(t['target'],self.dimensions(),legal)
            if phase == 'zip':
                ease = part * part * (3 - 2 * part)
                point = tuple(t['origin'][i] + (t['target'][i] - t['origin'][i]) * ease for i in (0, 1))
                self.move(*map(round, nearest_visible(point, self.dimensions(), legal)))
            elif phase == 'recompile':
                self.move(*nearest_visible(t['target'], self.dimensions(), legal))
            if progress >= 1:
                self.commit_loop(now, t['state'])
                self._transition = None
                if self._pending:
                    state, target = self._pending
                    self._pending = None
                    self.morph(state, target)
            self.update()
            return
        # Chat, dragging and the movement pause never stop sprite frame playback.
        self.advance_loop(now)
        if self._bubble and now >= self._bubble_until:
            self._bubble = ''
            self.update()
        if self._drag is not None:
            return
        observed = self.cursor.observation(now)
        changed = self.interactions.update(observed.get('over_sprite',False),now,self.config['mouse_reactions'])
        if changed == 'base':
            self.morph(self.base_state(),target=(self.x(),self.y()))
            return
        if changed:
            self.play_reaction(changed)
            return
        if self.interactions.active or self.watching or now < self._pause_until:
            return
        if self.behavior is not None and self.config['mouse_reactions']:
            policy = self.behavior if self.config['personality_behavior'] else self._neutral_behavior
            observed = self.cursor.observation(now)
            if (any(loop.name == 'waving' for loop in self.loops.get(self._logical_state, []))
                    and policy.greet_cursor(observed, now, self._logical_state, self.loop.name)):
                # Keep a hovered sprite under the pointer so clicking/dragging still works.
                target = (self.x(), self.y()) if observed.get('over_sprite') else None
                self.morph(loop_name='waving', target=target)
                return
        # No independent roaming timer: only selecting another visual loop can
        # trigger automatic chaos travel. Single-loop states keep playing in place.
        if now >= self._switch_next:
            self.morph()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        size = self.config['size']
        sx = sy = size / 192
        xoff, yoff = 45, 80
        if self._transition:
            t = self._transition
            progress = (time.monotonic() - t['start']) / t['duration']
            clip=t.get('clip')
            if clip:
                source=clip.frames[clip.index(progress*clip.duration,repeat=False)]
                box=QRect(xoff,yoff,size,round(size*208/192))
                # The pack's transition uses the seated base. Blend its bookends
                # with the current/next activity, without shifting either anchor.
                blend=(max(0.,1-progress/.12) if progress<.12
                       else max(0.,(progress-.88)/.12) if progress>.88 else 0.)
                painter.setOpacity(1-min(1.,blend))
                painter.drawPixmap(box,source)
                if blend:
                    painter.setOpacity(min(1.,blend))
                    painter.drawPixmap(box,self.pose if progress<.12 else self._next_pose)
                painter.setOpacity(1)
                self.paint_bubble(painter)
                return
            phase, part = self.motion_phase(progress)
            spread = part if phase == 'decompile' else 1 - part if phase == 'recompile' else 1
            source = self.pose if phase == 'decompile' else self._next_pose
            for x, y, dx, dy, weight in self._pieces:
                # Strong horizontal tearing plus sampled-pixel debris during travel.
                jitter = math.sin(progress * 85 + weight * 30) * spread * 18
                px = xoff + x * sx + dx * spread + jitter
                py = yoff + y * sy + dy * spread
                painter.setOpacity(max(.18, 1 - spread * weight * .7))
                painter.drawPixmap(QRect(round(px), round(py), max(1, round(16 * sx)), max(1, round(16 * sy))),
                                   source, QRect(x, y, min(16, 192 - x), min(16, 208 - y)))
        else:
            painter.drawPixmap(QRect(xoff, yoff, size, round(size * 208 / 192)), self.pose)
        painter.setOpacity(1)
        self.paint_bubble(painter)

    def paint_bubble(self,painter):
        if self._bubble and time.monotonic() < self._bubble_until:
            box = QRect(8, 5, self.width() - 16, 62)
            painter.setBrush(QColor('#171322'))
            painter.setPen(QColor('#cf297c'))
            painter.drawRoundedRect(box, 12, 12)
            painter.setPen(QColor('#d4f8e4'))
            painter.drawText(box.adjusted(10, 6, -10, -6), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter, self._bubble)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point=event.globalPosition().toPoint()
            if not self.hit_sprite((point.x(),point.y())):
                return
            self._pressed = event.globalPosition().toPoint()
            self._drag = self._pressed - self.pos()
            self._drag_moved = False
            self._last_interaction = time.monotonic()
            # Finish a current transition before a manual drag takes control.
            if self._transition:
                self.commit_loop(time.monotonic(), self._transition['state'])
                self._transition = None

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            if self._pressed is not None and (event.globalPosition().toPoint()-self._pressed).manhattanLength()>=8:
                self._drag_moved=True
            if not self._drag_moved:
                return
            p = event.globalPosition().toPoint() - self._drag
            legal=self.travel_areas()
            if legal:self.move(*nearest_visible((p.x(), p.y()), self.dimensions(),legal))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pressed is not None:
            clicked = not self._drag_moved and (event.globalPosition().toPoint() - self._pressed).manhattanLength() < 8
            self._drag = self._pressed = None
            self._pause_until = time.monotonic() + 8
            if self._pending:
                state, target = self._pending
                self._pending = None
                self.morph(state, target)
            if clicked:
                if not self.poke():
                    self.chat_requested.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button()==Qt.MouseButton.LeftButton:
            self._drag=self._pressed=None
            self._pause_until=time.monotonic()+8
            self.chat_requested.emit()

    def contextMenuEvent(self, event):
        self._pause_until = time.monotonic() + 30
        menu = QMenu(self)
        menu.addAction('Chat with Capri', self.chat_requested.emit)
        menu.addAction('Poke Capri', self.poke)
        menu.addAction('Memory and activity journal', self.memory_requested.emit)
        roam = menu.addAction('Roam across screens')
        roam.setCheckable(True)
        roam.setChecked(self.config['roaming'])
        roam.toggled.connect(lambda v: self.change_config('roaming', v))
        quiet = menu.addAction('Quiet mode')
        quiet.setCheckable(True)
        quiet.setChecked(self.config['quiet'])
        quiet.toggled.connect(lambda v: self.change_config('quiet', v))
        screens = menu.addMenu('Zip to screen')
        for i, screen in enumerate(QApplication.screens()):
            action=screens.addAction(f'{i + 1}: {screen.name()}', lambda index=i: self.teleport_to_screen(index))
            action.setEnabled(self.areas()[i] in self.travel_areas())
        protect=menu.addMenu('Protect media screen')
        for i,screen in enumerate(QApplication.screens()):
            action=protect.addAction(f'{i+1}: {screen.name()}')
            action.setCheckable(True)
            action.setChecked(screen_key(self.areas()[i]) in self.config['protected_media_screens'])
            action.toggled.connect(lambda enabled,index=i:self.protect_screen(index,enabled))
        if self.watching:menu.addAction('Stop watching media',self.stop_watching_requested.emit)
        library=menu.addMenu('Animation library')
        for state in sorted(self.loops):
            if state.startswith('library:'):
                label=state.removeprefix('library:').replace(':',' / ')
                library.addAction(label,lambda chosen=state:self.select_library_animation(chosen))
        menu.addAction('Switch animation loop', lambda: self.morph())
        menu.addSeparator()
        menu.addAction('Quit Capri', self.quit_requested.emit)
        menu.exec(event.globalPos())
        self._pause_until = time.monotonic() + 5

    def change_config(self, name, value):
        self.config.set(name, value)
        self.config_changed.emit()
