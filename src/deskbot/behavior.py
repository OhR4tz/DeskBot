"""One pose owner at a time: reaction overrides tracking until it completes."""
from __future__ import annotations

import math

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
        self.path: list[tuple[float, Pose]] = []
        self.path_index = 0
        self.path_arrived: float | None = None
        self.path_hold = 0.0

    def trigger(self, kind: str, now: float, pose: Pose) -> bool:
        if self.kind is not None or kind not in ("rock_on", "thumbs_down", "thumbs_up", "middle_finger"):
            return False
        self.kind = kind
        self.started = now
        self.origin = pose
        self.downcast_hold_started = None
        self.downcast_returning = False
        self.path = []
        self.path_index = 0
        self.path_arrived = None
        self.path_hold = 0.12 if kind == "rock_on" else 0.0
        points = []
        if kind == "rock_on":
            # Three pure tilt nods. Reverse the first stroke near the lower limit.
            tilt = self.config.tilt
            down_room = pose.tilt - tilt.minimum
            up_room = tilt.maximum - pose.tilt
            delta = -15 if down_room >= 15 or down_room >= up_room else 15
            nod = Pose(pose.pan, tilt.clamp(pose.tilt + delta))
            points = [nod, pose] * 3
        elif kind == "thumbs_up":
            # Shift a modest ellipse inward near an endpoint, keeping its entire
            # path away from the configured limits, then return to the origin.
            def circle_axis(axis, origin, radius):
                margin = min(2.0, (axis.maximum - axis.minimum) * 0.1)
                radius = min(radius, (axis.maximum - axis.minimum) / 2 - margin)
                center = max(axis.minimum + radius + margin,
                             min(axis.maximum - radius - margin, origin))
                return center, radius
            pan, pan_radius = circle_axis(self.config.pan, pose.pan, 12)
            tilt, tilt_radius = circle_axis(self.config.tilt, pose.tilt, 10)
            points = [Pose(pan + pan_radius * math.cos(i * math.tau / 16),
                           tilt + tilt_radius * math.sin(i * math.tau / 16))
                      for i in range(17)] + [pose]
        previous = pose
        deadline = 0.0
        for point in points:
            deadline += max(abs(point.pan - previous.pan), abs(point.tilt - previous.tilt)) / self.config.max_speed + self.path_hold
            self.path.append((deadline, point))
            previous = point
        return True

    def pose(self, now: float, tracking: Pose, current: Pose | None = None) -> Pose:
        if self.kind is None:
            return tracking
        elapsed = max(0.0, now - self.started)
        if self.path:
            while self.path_index < len(self.path):
                deadline, goal = self.path[self.path_index]
                if current is None:
                    if elapsed < deadline:
                        return goal
                else:
                    if abs(current.pan - goal.pan) > 0.01 or abs(current.tilt - goal.tilt) > 0.01:
                        self.path_arrived = None
                        return goal
                    if self.path_arrived is None:
                        self.path_arrived = now
                    if now - self.path_arrived < self.path_hold:
                        return goal
                self.path_index += 1
                self.path_arrived = None
            self.kind = None
            return tracking
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
