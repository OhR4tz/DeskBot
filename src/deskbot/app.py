"""Camera, gesture, behavior and motion orchestration."""
from __future__ import annotations

import time
import signal
from typing import Any

from .behavior import Behavior
from .config import Config
from .gesture import GestureGate, classify
from .motion import Motion, Pose
from .tracking import Box, TargetTracker


class Robot:
    def __init__(self, config: Config, motion: Motion | None = None) -> None:
        self.config = config
        self.motion = motion
        self.tracker = TargetTracker(config)
        self.behavior = Behavior(config)
        self.gates = [GestureGate(config.gesture_frames, config.gesture_cooldown)
                      for _ in range(2)]
        self.hand_positions: list[tuple[float, float] | None] = [None, None]
        self.target = Pose()
        self.last_step: float | None = None
        self.last_status = 0.0
        self.last_reaction = float("-inf")

    def process(self, frame: Any, now: float) -> tuple[str, Pose]:
        too_old = (frame.captured_at is not None and
                   now - frame.captured_at > self.config.inference_timeout)
        detections = None if too_old else frame.detections
        hands = [] if too_old else frame.hands
        selected = self.tracker.select(detections, now)
        fresh = (detections is not None and
                 self.tracker.last_seen == now and selected is not None)
        if fresh:
            self.target = self.tracker.aim(self.motion.pose if self.motion else self.target)
        elif selected is None:
            self.target = self.motion.pose if self.motion else self.target
            self.behavior.kind = None
        # Assign by wrist proximity, since MediaPipe result order can swap.
        matched: dict[int, Any] = {}
        used: set[int] = set()
        for hand in hands:
            if not hand:
                continue
            wrist = hand[0]
            choices = [(i, (wrist.x - old[0])**2 + (wrist.y - old[1])**2)
                       for i, old in enumerate(self.hand_positions)
                       if old is not None and i not in used]
            if choices:
                i, distance = min(choices, key=lambda pair: pair[1])
                if distance <= 0.18**2:
                    matched[i] = hand
                    used.add(i)
                    continue
            for i in range(len(self.gates)):
                if i not in used and self.hand_positions[i] is None:
                    matched[i] = hand
                    used.add(i)
                    break
        # Associate hands only with the selected person's region.
        for i, gate in enumerate(self.gates):
            hand = matched.get(i)
            kind = None
            if hand is not None and selected is not None and fresh:
                wrist = hand[0]
                if selected.contains(wrist.x * self.config.width,
                                     wrist.y * self.config.height,
                                     margin=0.12 * max(selected.width, selected.height)):
                    kind = classify(hand, self.config.height / self.config.width)
            self.hand_positions[i] = (hand[0].x, hand[0].y) if hand else None
            can_react = (self.behavior.kind is None and
                         now - self.last_reaction >= self.config.gesture_cooldown)
            event = gate.update(kind, now, enabled=can_react)
            if event:
                if self.behavior.trigger(event, now, self.motion.pose if self.motion else self.target):
                    self.last_reaction = now
        goal = self.behavior.pose(now, self.target)
        if self.motion is not None:
            dt = 0.0 if self.last_step is None else now - self.last_step
            self.motion.step(goal, dt)
        self.last_step = now
        status = (f"person={'yes' if fresh else 'stale' if selected else 'no'} "
                  f"hands={len(hands)} reaction={self.behavior.kind or '-'} "
                  f"target=({goal.pan:+.1f},{goal.tilt:+.1f})")
        return status, goal


def run(config: Config, *, hardware: bool, preview: bool = False,
        observe_only: bool = False) -> None:
    if hardware and (observe_only or not config.calibrated):
        raise ValueError("hardware run requires calibrated = true and no observation mode")
    from .vision import CameraVision
    from .motion import CrickitServos, FakeServos
    def stop_on_term(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    previous_term = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, stop_on_term)
    motion = None
    cv2 = None
    try:
        motion = None if observe_only else Motion(config, CrickitServos(config) if hardware else FakeServos())
        robot = Robot(config, motion)
        if preview:
            import cv2
        with CameraVision(config, hands=True) as vision:
            if motion:
                motion.start()
            while True:
                frame = vision.capture()
                now = time.monotonic()
                status, _ = robot.process(frame, now)
                if now - robot.last_status >= 1.0:
                    print(status, flush=True)
                    robot.last_status = now
                if preview:
                    display = cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2BGR)
                    box = robot.tracker.selected
                    if box:
                        cv2.rectangle(display, (int(box.x), int(box.y)),
                                      (int(box.x + box.width), int(box.y + box.height)),
                                      (0, 255, 0), 2)
                    cv2.imshow("DeskBot (q to quit)", display)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if motion:
                motion.close()
        finally:
            try:
                if cv2 is not None:
                    cv2.destroyAllWindows()
            finally:
                signal.signal(signal.SIGTERM, previous_term)
