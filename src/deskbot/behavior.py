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
        self.downcast_hold_started: float | None = None
        self.downcast_returning = False

    def trigger(self, kind: str, now: float, pose: Pose) -> bool:
        if self.kind is not None or kind not in ("rock_on", "middle_finger"):
            return False
        self.kind = kind
        self.started = now
        self.origin = pose
        self.downcast_hold_started = None
        self.downcast_returning = False
        return True

    def pose(self, now: float, tracking: Pose, current: Pose | None = None) -> Pose:
        if self.kind is None:
            return tracking
        elapsed = max(0.0, now - self.started)
        if self.kind == "middle_finger":
            down = Pose(self.origin.pan, self.config.tilt.minimum)
            if current is None:
                # Observation mode has no commanded motion to report arrival.
                travel = abs(self.origin.tilt - down.tilt) / self.config.max_speed
                if elapsed < travel + 0.8:
                    return down
                if elapsed < 2 * travel + 0.8:
                    return self.origin
            elif not self.downcast_returning:
                if abs(current.tilt - down.tilt) > 0.01:
                    return down
                if self.downcast_hold_started is None:
                    self.downcast_hold_started = now
                if now - self.downcast_hold_started < 0.8:
                    return down
                self.downcast_returning = True
                return self.origin
            elif (abs(current.tilt - self.origin.tilt) > 0.01 or
                  abs(current.pan - self.origin.pan) > 0.01):
                return self.origin
            self.kind = None
            return tracking
        else:
            # Happy nod with modest pan wiggle, held inside calibrated bounds.
            sequence = ((0.25, 0, 5), (0.50, 5, -3), (0.75, -5, 5),
                        (1.00, 5, -3), (1.25, -5, 4), (1.50, 0, 0))
        for end, pan_delta, tilt_delta in sequence:
            if elapsed < end:
                return Pose(self.config.pan.clamp(self.origin.pan + pan_delta),
                            self.config.tilt.clamp(self.origin.tilt + tilt_delta))
        self.kind = None
        return tracking
