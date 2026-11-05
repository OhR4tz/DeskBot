"""Conservative pose heuristics; monocular depth only suggests forward pointing."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float = 0.0


def _angle(a: Point, b: Point, c: Point, aspect: float) -> float:
    # MediaPipe x and z use image width; y uses image height.
    # Correct y for the image aspect before measuring 3D finger bend.
    v = (a.x - b.x, (a.y - b.y) * aspect, a.z - b.z)
    w = (c.x - b.x, (c.y - b.y) * aspect, c.z - b.z)
    lengths = math.sqrt(sum(t*t for t in v) * sum(t*t for t in w))
    if lengths < 1e-8:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(i*j for i, j in zip(v, w)) / lengths))))


def _distance(a: Point, b: Point, aspect: float) -> float:
    return math.hypot(a.x - b.x, (a.y - b.y) * aspect)


def classify(hand: Sequence[Point], aspect: float = 0.75) -> str | None:
    if len(hand) != 21:
        return None
    if not math.isfinite(aspect) or aspect <= 0:
        return None
    if not all(math.isfinite(p.x) and math.isfinite(p.y) and math.isfinite(p.z) for p in hand):
        return None
    # MCP/PIP/TIP indices for index, middle, ring, little fingers.
    joints = ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))
    angles = [_angle(hand[m], hand[p], hand[t], aspect) for m, p, t in joints]
    straight = [a >= 150 for a in angles]
    curled = [a <= 115 for a in angles]
    palm = max(_distance(hand[5], hand[17], aspect), 1e-5)
    thumb_extended = (_distance(hand[4], hand[17], aspect) > 1.35 * palm and
                      _angle(hand[2], hand[3], hand[4], aspect) > 140)
    thumb_folded = _distance(hand[4], hand[9], aspect) < 0.95 * palm
    if straight[0] and curled[1] and curled[2] and straight[3] and thumb_folded:
        return "rock_on"
    if straight[0] and curled[1] and curled[2] and curled[3] and thumb_extended:
        # Relative depth and foreshortening together suggest pointing at the lens.
        index_depth = hand[8].z - hand[5].z
        apparent_length = _distance(hand[8], hand[5], aspect) / palm
        if index_depth < -0.30 * palm and apparent_length < 1.25:
            return "finger_gun"
    return None


class GestureGate:
    def __init__(self, frames: int, cooldown: float) -> None:
        self.frames = frames
        self.cooldown = cooldown
        self.last_kind: str | None = None
        self.count = 0
        self.armed = True
        self.last_trigger = float("-inf")

    def update(self, kind: str | None, now: float, *, enabled: bool = True) -> str | None:
        if kind is None:
            self.last_kind = None
            self.count = 0
            self.armed = True
            return None
        if kind == self.last_kind:
            self.count += 1
        else:
            self.last_kind = kind
            self.count = 1
        if enabled and self.armed and self.count >= self.frames and now - self.last_trigger >= self.cooldown:
            self.last_trigger = now
            self.armed = False
            return kind
        return None
