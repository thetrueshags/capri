"""Logical screen geometry, including negative origins and mixed screen layouts."""
from dataclasses import dataclass
import math
import random

@dataclass(frozen=True)
class Area:
    x: int
    y: int
    width: int
    height: int

    def clamp(self, point, size):
        w, h = size
        return (max(self.x, min(point[0], self.x + max(0, self.width - w))),
                max(self.y, min(point[1], self.y + max(0, self.height - h))))

    def contains(self, point, size):
        return self.clamp(point, size) == point

def nearest_visible(point, size, areas):
    if not areas:
        raise ValueError('At least one screen is required')
    candidates = [a.clamp(point, size) for a in areas]
    return min(candidates, key=lambda p: math.dist(p, point))

def destination(areas, size, rng=None, preferred=None):
    rng = rng or random
    area = preferred or rng.choice(areas)
    max_x = area.x + max(0, area.width - size[0])
    max_y = area.y + max(0, area.height - size[1])
    return (rng.randint(area.x, max_x), rng.randint(max(area.y, max_y - 100), max_y))

def transition_phase(progress):
    progress = max(0., min(1., progress))
    if progress < .3:
        return 'decompile', progress / .3
    if progress < .65:
        return 'zip', (progress - .3) / .35
    return 'recompile', (progress - .65) / .35

