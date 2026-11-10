"""Small TOML configuration with explicit motion safety validation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import json
import math
import os
import tomllib


@dataclass(frozen=True)
class Axis:
    center: float
    direction: int
    minimum: float
    maximum: float
    pulse_min: int = 750
    pulse_max: int = 2250

    def validate(self, name: str) -> None:
        numbers = (self.center, self.minimum, self.maximum)
        if not all(math.isfinite(x) for x in numbers):
            raise ValueError(f"{name}: angles must be finite")
        if self.direction not in (-1, 1):
            raise ValueError(f"{name}: direction must be -1 or 1")
        if not (self.minimum < 0 < self.maximum):
            raise ValueError(f"{name}: range must straddle zero")
        envelope = 70 if name == "pan" else 60
        if self.minimum < -envelope or self.maximum > envelope:
            raise ValueError(f"{name}: range exceeds mechanical +/-{envelope} degree envelope")
        servo_ends = (self.center + self.direction * self.minimum,
                      self.center + self.direction * self.maximum)
        if not (0 <= self.center <= 180 and all(0 <= x <= 180 for x in servo_ends)):
            raise ValueError(f"{name}: configured motion exceeds servo angle 0..180")
        if not (500 <= self.pulse_min < self.pulse_max <= 2500):
            raise ValueError(f"{name}: pulse range must lie within 500..2500 us")

    def clamp(self, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("motion target must be finite")
        return min(self.maximum, max(self.minimum, value))

    def servo_angle(self, world_angle: float) -> float:
        return self.center + self.direction * self.clamp(world_angle)


@dataclass(frozen=True)
class Config:
    pan: Axis
    tilt: Axis
    calibrated: bool
    model: str
    hand_model: str
    width: int = 640
    height: int = 480
    fps: int = 10
    max_hands: int = 1
    person_threshold: float = 0.55
    deadband: float = 0.065
    pan_gain: float = 0.18
    tilt_gain: float = 0.12
    max_speed: float = 28.0
    inference_timeout: float = 0.8
    lost_timeout: float = 1.2
    gesture_frames: int = 3
    gesture_cooldown: float = 3.0

    def validate(self) -> None:
        self.pan.validate("pan")
        self.tilt.validate("tilt")
        if type(self.calibrated) is not bool:
            raise ValueError("calibrated must be a boolean")
        if self.width < 160 or self.height < 120:
            raise ValueError("image size too small")
        if type(self.fps) is not int or not 1 <= self.fps <= 30:
            raise ValueError("fps must be 1..30")
        if type(self.max_hands) is not int or self.max_hands not in (1, 2):
            raise ValueError("max_hands must be 1 or 2")
        for key in ("person_threshold", "deadband", "pan_gain", "tilt_gain",
                    "max_speed", "inference_timeout", "lost_timeout", "gesture_cooldown"):
            value = getattr(self, key)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be positive and finite")
        if not (0 < self.person_threshold < 1 and self.deadband < 0.5):
            raise ValueError("person_threshold/deadband out of range")
        if self.max_speed > 90 or self.pan_gain > 2 or self.tilt_gain > 2:
            raise ValueError("motion speed/gain exceeds conservative limit")
        if self.gesture_frames < 2 or self.gesture_frames > 15:
            raise ValueError("gesture_frames must be 2..15")
        if not self.model or not self.hand_model:
            raise ValueError("model paths cannot be empty")


def load(path: str | Path) -> Config:
    with open(path, "rb") as stream:
        data = tomllib.load(stream)
    allowed_top = {"calibrated", "model", "hand_model", "width", "height", "fps", "max_hands",
                   "person_threshold", "deadband", "pan_gain", "tilt_gain", "max_speed",
                   "inference_timeout", "lost_timeout", "gesture_frames", "gesture_cooldown",
                   "pan", "tilt"}
    extra = set(data) - allowed_top
    if extra:
        raise ValueError(f"unknown config keys: {sorted(extra)}")
    axis_fields = set(Axis.__dataclass_fields__)
    for name in ("pan", "tilt"):
        if name not in data or set(data[name]) - axis_fields:
            raise ValueError(f"{name}: missing axis or unknown keys")
    try:
        config = Config(**{**{k: v for k, v in data.items() if k not in ("pan", "tilt")},
                           "pan": Axis(**data["pan"]), "tilt": Axis(**data["tilt"])})
    except TypeError as error:
        raise ValueError(f"invalid config structure: {error}") from error
    config.validate()
    return config


def with_axis(config: Config, name: str, **changes: float | int) -> Config:
    if name not in ("pan", "tilt"):
        raise ValueError("axis must be pan or tilt")
    new = replace(config, **{name: replace(getattr(config, name), **changes), "calibrated": False})
    new.validate()
    return new


def save(path: str | Path, config: Config) -> None:
    """Write only known keys; a changed calibration always needs explicit re-arm."""
    config.validate()
    text = [
        "# Validate clearance on the assembled head before setting calibrated = true.",
        f"calibrated = {str(config.calibrated).lower()}",
        f"model = {json.dumps(config.model)}",
        f"hand_model = {json.dumps(config.hand_model)}",
    ]
    for key in ("width", "height", "fps", "max_hands", "person_threshold", "deadband", "pan_gain",
                "tilt_gain", "max_speed", "inference_timeout", "lost_timeout",
                "gesture_frames", "gesture_cooldown"):
        text.append(f"{key} = {getattr(config, key)}")
    for name in ("pan", "tilt"):
        axis = getattr(config, name)
        text.extend(("", f"[{name}]"))
        for key in axis_fields_order:
            text.append(f"{key} = {getattr(axis, key)}")
    target = Path(path)
    staged = target.with_name(target.name + ".new")
    staged.write_text("\n".join(text) + "\n", encoding="utf-8")
    os.replace(staged, target)


axis_fields_order = ("center", "direction", "minimum", "maximum", "pulse_min", "pulse_max")
