"""Inspectable nonverbal policy: persona traits appraise real cursor observations."""
from dataclasses import asdict, dataclass
import math
import random
from .motion import destination

@dataclass(frozen=True)
class BehaviorProfile:
    energy: float = .5
    curiosity: float = .5
    playfulness: float = .5
    affection: float = .5
    patience: float = .5
    personal_space: float = .5

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError('Personality behavior must be an object')
        values = {}
        for key in cls.__dataclass_fields__:
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Missing or invalid behavior trait: ' + key)
            values[key] = max(0., min(1., float(value)))
        return cls(**values)

    def as_dict(self):
        return asdict(self)

class CursorTracker:
    """Position samples stay in memory; no pointer trail or screen capture."""
    def __init__(self):
        self.enabled = False
        self.position = None
        self.screen = ''
        self.screen_index = None
        self.sampled = None
        self.last_motion = None
        self.speed = 0.
        self.near_since = None
        self.distance = None
        self.hovering = False
        self.direction = 'unknown'

    def disable(self):
        self.__init__()

    def sample(self, point, screen, screen_index, pet_rect, now, over_sprite=None):
        self.enabled = True
        if self.position is not None and self.sampled is not None:
            delta = math.dist(point, self.position)
            elapsed = max(.001, now - self.sampled)
            self.speed = delta / elapsed
            if delta >= 2:
                self.last_motion = now
        else:
            self.speed = 0.
            self.last_motion = now
        self.position = tuple(point)
        self.screen, self.screen_index = screen, screen_index
        self.sampled = now
        x, y, w, h = pet_rect
        center = (x + w / 2, y + h / 2)
        self.distance = math.dist(point, center)
        self.hovering = (x <= point[0] < x + w and y <= point[1] < y + h) if over_sprite is None else bool(over_sprite)
        if self.distance < 220:
            if self.near_since is None:
                self.near_since = now
        else:
            self.near_since = None
        dx, dy = point[0] - center[0], point[1] - center[1]
        vertical = 'above' if dy < -30 else 'below' if dy > 30 else ''
        horizontal = 'left' if dx < -30 else 'right' if dx > 30 else ''
        self.direction = '-'.join(p for p in (vertical, horizontal) if p) or 'overlapping'

    def observation(self, now):
        if not self.enabled or self.sampled is None or now - self.sampled > 2:
            return {'enabled': False}
        return {'enabled': True, 'position': list(self.position), 'screen': self.screen,
                'screen_index': self.screen_index, 'distance_to_capri': round(self.distance, 1),
                'direction_from_capri': self.direction, 'over_sprite': self.hovering,
                'speed': round(self.speed, 1), 'moving': self.speed >= 15,
                'idle_seconds': round(max(0., now - self.last_motion), 1),
                'near_seconds': round(now - self.near_since, 1) if self.near_since is not None else 0,
                'sample_age_seconds': round(max(0., now - self.sampled), 2)}

class BehaviorEngine:
    def __init__(self, profile=None):
        self.profile = profile or BehaviorProfile()
        self._next_greeting = 0.
        self._greeted_visit = False

    def switch_delay(self, low, high, rng):
        p = self.profile
        factor = 1.35 - .75 * p.energy - .25 * p.playfulness
        return max(5., rng.uniform(low, max(low, high)) * factor)

    def transition_duration(self, base):
        return max(.35, min(1.8, base * (1.3 - .6 * self.profile.energy)))

    def sleep_delay(self, base):
        return max(60., base * (.8 + .8 * self.profile.energy))

    def loop_weights(self, names, cursor=None):
        p = self.profile
        near = bool(cursor and cursor.get('enabled') and cursor.get('distance_to_capri', 9999) < 220)
        weights = {'meditating': .5 + 2 * p.patience + 2 * (1 - p.energy),
                   'floating': .5 + p.curiosity + p.energy + p.playfulness,
                   'waving': .2 + 2 * p.affection + 1.5 * p.playfulness + int(near),
                   'bored': .3+1.5*(1-p.energy),
                   'stretching': .3+p.energy,
                   'coffee': .5+p.patience,
                   'reading': .5+2*p.curiosity+p.patience,
                   'searching': .2+2*p.curiosity,
                   'success': .5+p.playfulness,
                   'excited': .2+2*p.energy+p.playfulness,
                   'poke': .4+3*p.affection+p.playfulness,
                   'poke-annoyed': .1+1.5*p.personal_space+(1-p.patience),
                   'typing': 1., 'dizzy': 1., 'sleeping': 1.}
        return [weights.get(name, 1.) for name in names]

    def choose_loop(self, alternatives, rng, cursor=None):
        return rng.choices(alternatives, self.loop_weights([loop.name for loop in alternatives], cursor), k=1)[0]

    def greet_cursor(self, observation, now, state, current_loop):
        near = (observation.get('enabled') and observation.get('distance_to_capri', 9999) < 220)
        if not near:
            self._greeted_visit = False
            return False
        p = self.profile
        if state not in ('idle', 'ready') or current_loop == 'waving' or self._greeted_visit or now < self._next_greeting:
            return False
        if observation.get('near_seconds', 0) < 1 or observation.get('speed', 0) > 250:
            return False
        if p.affection + p.playfulness < .65:
            return False
        self._greeted_visit = True
        self._next_greeting = now + 60 + 120 * p.patience
        return True

    def choose_destination(self, areas, size, rng, cursor=None):
        cursor = cursor or {}
        point = tuple(cursor['position']) if cursor.get('enabled') else None
        p = self.profile
        near_mouse = point is not None and rng.random() < .25 + .65 * p.curiosity
        if near_mouse:
            # Choose the actual cursor monitor even with negative origins/scaling gaps.
            area = min(areas, key=lambda a: math.dist(a.clamp(point, (0, 0)), point))
            radius = 220 + 180 * p.personal_space
            for _ in range(32):
                angle = rng.uniform(0, 2 * math.pi)
                center = (point[0] + math.cos(angle) * radius, point[1] + math.sin(angle) * radius)
                candidate = area.clamp((center[0] - size[0] / 2, center[1] - size[1] / 2), size)
                if self.clear_of_pointer(candidate, size, point):
                    return tuple(map(round, candidate))
        for _ in range(32):
            candidate = destination(areas, size, rng)
            if point is None or self.clear_of_pointer(candidate, size, point):
                return candidate
        # Tiny screens may have no completely clear perch; choose the farthest legal corner.
        candidates = [a.clamp((x, y), size) for a in areas
                      for x in (a.x, a.x + a.width) for y in (a.y, a.y + a.height)]
        return max(candidates, key=lambda c: math.dist(c, point)) if point is not None else candidates[0]

    @staticmethod
    def clear_of_pointer(candidate, size, pointer):
        x, y = candidate
        return not (x - 32 <= pointer[0] < x + size[0] + 32 and y - 32 <= pointer[1] < y + size[1] + 32)
