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
    def __init__(self, config: Config, aim_fraction: float = 0.28) -> None:
        self.config = config
        self.aim_fraction = aim_fraction
        self.selected: Box | None = None
        self.last_seen = float("-inf")
        self.smoothed: tuple[float, float] | None = None
        self.last_aim: float | None = None
        self.velocity = (0.0, 0.0)

    def reset_motion(self) -> None:
        self.last_aim = None
        self.velocity = (0.0, 0.0)

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
        bx = chosen.box.center[0]
        by = chosen.box.y + self.aim_fraction * chosen.box.height
        if self.smoothed is None:
            self.smoothed = (bx, by)
        else:
            # Damp detector noise, but avoid dragging old coordinates behind a
            # moving face (or behind the camera's own movement).
            self.smoothed = tuple(old + (0.75 if abs(new - old) > 10 else 0.2) * (new - old)
                                  for old, new in zip(self.smoothed, (bx, by)))
        return self.selected

    def aim(self, current: Pose, now: float | None = None) -> Pose:
        if self.smoothed is None:
            return current
        x, y = self.smoothed
        ex = (x - self.config.width / 2) / (self.config.width / 2)
        ey = (y - self.config.height / 2) / (self.config.height / 2)
        # A continuous deadband avoids a sudden correction at its boundary.
        ex = math.copysign(max(0.0, abs(ex) - self.config.deadband), ex)
        ey = math.copysign(max(0.0, abs(ey) - self.config.deadband), ey)
        dt = 1 / self.config.fps if now is None or self.last_aim is None else min(0.25, max(0.0, now - self.last_aim))
        self.last_aim = now
        wanted = (-ex * self.config.pan_gain * 100, -ey * self.config.tilt_gain * 100)
        # Ease changes in tracking velocity; gesture motion has its own owner.
        ramp = 120 * dt
        self.velocity = tuple(old + max(-ramp, min(ramp, max(-self.config.max_speed,
                              min(self.config.max_speed, new)) - old))
                              for old, new in zip(self.velocity, wanted))
        # Calibrated world +pan points left, +tilt points up.
        # The unmirrored camera's image +x points right and +y points down.
        return Pose(self.config.pan.clamp(current.pan + self.velocity[0] * dt),
                    self.config.tilt.clamp(current.tilt + self.velocity[1] * dt))
