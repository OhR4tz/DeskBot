"""Choose one prominent person and turn image error into small head corrections."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .config import Config
from .motion import Pose


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def contains(self, x: float, y: float, margin: float = 0) -> bool:
        return (self.x - margin <= x <= self.x + self.width + margin and
                self.y - margin <= y <= self.y + self.height + margin)


@dataclass(frozen=True)
class Detection:
    box: Box
    score: float


class TargetTracker:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.selected: Box | None = None
        self.last_seen = float("-inf")
        self.smoothed: tuple[float, float] | None = None

    def select(self, detections: list[Detection] | None, now: float) -> Box | None:
        # None means no new inference. Never reuse it beyond the stale timeout.
        if detections is None:
            if now - self.last_seen > self.config.inference_timeout:
                self.selected = None
                self.smoothed = None
            return self.selected
        candidates = [d for d in detections if d.score >= self.config.person_threshold
                      and d.box.area > 0]
        if not candidates:
            if now - self.last_seen > self.config.lost_timeout:
                self.selected = None
                self.smoothed = None
            return self.selected
        if self.selected is None or now - self.last_seen > self.config.lost_timeout:
            chosen = max(candidates, key=lambda d: d.box.area * d.score)
        else:
            cx, cy = self.selected.center
            size = max(self.selected.width, self.selected.height, 1)
            ranked = sorted(candidates, key=lambda d: math.dist(d.box.center, (cx, cy)) / size)
            nearest = ranked[0]
            if math.dist(nearest.box.center, (cx, cy)) / size < 0.8:
                chosen = nearest
            else:
                # Suppress jumps to another person until the old target expires.
                return self.selected
        self.selected = chosen.box
        self.last_seen = now
        bx, by = chosen.box.center
        if self.smoothed is None:
            self.smoothed = (bx, by)
        else:
            self.smoothed = (0.65 * self.smoothed[0] + 0.35 * bx,
                             0.65 * self.smoothed[1] + 0.35 * by)
        return self.selected

    def aim(self, current: Pose) -> Pose:
        if self.smoothed is None:
            return current
        # Aim at upper body/head region, since the IMX500 model gives person boxes.
        x = self.smoothed[0]
        y = self.selected.y + 0.28 * self.selected.height if self.selected else self.smoothed[1]
        ex = (x - self.config.width / 2) / (self.config.width / 2)
        ey = (y - self.config.height / 2) / (self.config.height / 2)
        if abs(ex) < self.config.deadband:
            ex = 0
        if abs(ey) < self.config.deadband:
            ey = 0
        # Calibrated world +pan points left, +tilt points up.
        # The unmirrored camera's image +x points right and +y points down.
        return Pose(self.config.pan.clamp(current.pan - ex * self.config.pan_gain * 10),
                    self.config.tilt.clamp(current.tilt - ey * self.config.tilt_gain * 10))
