"""One pose owner at a time: reaction overrides tracking until it completes."""
from __future__ import annotations

from .config import Config
from .motion import Pose


class Behavior:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.kind: str | None = None
        self.started = 0.0
        self.origin = Pose()

    def trigger(self, kind: str, now: float, pose: Pose) -> bool:
        if self.kind is not None or kind not in ("rock_on", "finger_gun"):
            return False
        self.kind = kind
        self.started = now
        self.origin = pose
        return True

    def pose(self, now: float, tracking: Pose) -> Pose:
        if self.kind is None:
            return tracking
        elapsed = max(0.0, now - self.started)
        if self.kind == "rock_on":
            # Happy nod with modest pan wiggle, held inside calibrated bounds.
            sequence = ((0.25, 0, 5), (0.50, 5, -3), (0.75, -5, 5),
                        (1.00, 5, -3), (1.25, -5, 4), (1.50, 0, 0))
        else:
            # A subdued downcast glance and return.
            sequence = ((0.35, 0, -7), (0.85, 0, -7), (1.30, 0, 0))
        for end, pan_delta, tilt_delta in sequence:
            if elapsed < end:
                return Pose(self.config.pan.clamp(self.origin.pan + pan_delta),
                            self.config.tilt.clamp(self.origin.tilt + tilt_delta))
        self.kind = None
        return tracking
