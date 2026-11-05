"""Bounded world-relative pan/tilt; only this module touches servo hardware."""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import math

from .config import Config


@dataclass(frozen=True)
class Pose:
    pan: float = 0.0
    tilt: float = 0.0


class FakeServos:
    def __init__(self) -> None:
        self.angles: deque[tuple[float, float]] = deque(maxlen=16)

    def write(self, pan: float, tilt: float) -> None:
        self.angles.append((pan, tilt))

    def close(self) -> None:
        pass


class CrickitServos:
    def __init__(self, config: Config) -> None:
        # Import is deliberately delayed: observation and simulation work off-Pi.
        from adafruit_crickit import crickit
        self.pan = crickit.servo_1
        self.tilt = crickit.servo_2
        for servo, axis in ((self.pan, config.pan), (self.tilt, config.tilt)):
            servo.actuation_range = 180
            servo.set_pulse_width_range(min_pulse=axis.pulse_min, max_pulse=axis.pulse_max)

    def write(self, pan: float, tilt: float) -> None:
        self.pan.angle = pan
        self.tilt.angle = tilt

    def close(self) -> None:
        # Stop holding torque; do not drive to an unverified rest pose.
        first_error = None
        for servo in (self.pan, self.tilt):
            try:
                servo.angle = None
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error


class Motion:
    def __init__(self, config: Config, servos: FakeServos | CrickitServos) -> None:
        self.config = config
        self.servos = servos
        self.pose = Pose()
        self.started = False

    def start(self) -> None:
        # The operator must have manually placed the head near neutral before attaching.
        self.servos.write(self.config.pan.servo_angle(0), self.config.tilt.servo_angle(0))
        self.started = True

    def step(self, target: Pose, dt: float) -> Pose:
        if not self.started:
            raise RuntimeError("motion must be started explicitly")
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("invalid time step")
        dt = min(dt, 0.25)
        travel = self.config.max_speed * dt
        def advance(current: float, wanted: float, axis) -> float:
            wanted = axis.clamp(wanted)
            return axis.clamp(current + max(-travel, min(travel, wanted - current)))
        self.pose = Pose(advance(self.pose.pan, target.pan, self.config.pan),
                         advance(self.pose.tilt, target.tilt, self.config.tilt))
        self.servos.write(self.config.pan.servo_angle(self.pose.pan),
                          self.config.tilt.servo_angle(self.pose.tilt))
        return self.pose

    def close(self) -> None:
        self.servos.close()
