"""Camera, gesture, behavior and motion orchestration."""
from __future__ import annotations

import time
import signal
from dataclasses import replace
from typing import Any

from .behavior import Behavior
from .config import Config
from .gesture import GestureGate, classify
from .motion import Motion, Pose
from .tracking import Box, Detection, TargetTracker


class Robot:
    def __init__(self, config: Config, motion: Motion | None = None) -> None:
        self.config = config
        self.motion = motion
        self.tracker = TargetTracker(config)
        self.face_tracker = TargetTracker(
            replace(config, lost_timeout=0.4, inference_timeout=0.4), aim_fraction=0.5)
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
        faces = None if too_old else frame.faces
        face_detections = None if faces is None else [
            Detection(box, 1.0) for box in faces
            if selected is None or selected.contains(*box.center,
                margin=0.15 * max(selected.width, selected.height))]
        face = self.face_tracker.select(face_detections, now)
        fresh_face = face is not None and self.face_tracker.last_seen == now
        aim_tracker = self.face_tracker if fresh_face else self.tracker if face is None and fresh else None
        if aim_tracker is not None:
            self.target = aim_tracker.aim(self.motion.pose if self.motion else self.target, now)
        else:
            self.target = self.motion.pose if self.motion else self.target
        for tracker in (self.tracker, self.face_tracker):
            if tracker is not aim_tracker or self.behavior.kind is not None:
                tracker.reset_motion()
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
            if hand is not None and selected is not None and (fresh or fresh_face):
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
        goal = self.behavior.pose(now, self.target,
                                  self.motion.pose if self.motion else None)
        if self.motion is not None:
            dt = 0.0 if self.last_step is None else now - self.last_step
            self.motion.step(goal, dt)
        self.last_step = now
        status = (f"person={'yes' if fresh else 'stale' if selected else 'no'} "
                  f"face={'yes' if fresh_face else 'stale' if face else 'no'} "
                  f"aim={'face' if fresh_face else 'person' if aim_tracker else 'hold'} "
                  f"hands={len(hands)} reaction={self.behavior.kind or '-'} "
                  f"target=({goal.pan:+.1f},{goal.tilt:+.1f})")
        if fresh_face:
            cx, cy = face.center
            status += f" face_error_px=({cx - self.config.width / 2:+.0f},{cy - self.config.height / 2:+.0f})"
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
            window_started = time.monotonic()
            window_frames = 0
            while True:
                frame = vision.capture()
                now = time.monotonic()
                window_frames += 1
                status, _ = robot.process(frame, now)
                if now - robot.last_status >= 1.0:
                    fps = window_frames / max(now - window_started, 0.001)
                    print(f"fps={fps:.1f} {status}", flush=True)
                    robot.last_status = now
                    window_started = now
                    window_frames = 0
                if preview:
                    display = cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2BGR)
                    box = robot.tracker.selected
                    if box:
                        cv2.rectangle(display, (int(box.x), int(box.y)),
                                      (int(box.x + box.width), int(box.y + box.height)),
                                      (0, 255, 0), 2)
                    face = robot.face_tracker.selected
                    if face:
                        cv2.rectangle(display, (int(face.x), int(face.y)),
                                      (int(face.x + face.width), int(face.y + face.height)),
                                      (255, 180, 0), 2)
                    cv2.drawMarker(display, (config.width // 2, config.height // 2),
                                   (0, 255, 255), cv2.MARKER_CROSS, 18, 1)
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
