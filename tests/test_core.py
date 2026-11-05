import unittest
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path
import contextlib
import io
import signal

from deskbot.app import Robot, run
from deskbot.behavior import Behavior
from deskbot.cli import calibrate
from deskbot.config import Axis, Config, load, save
from deskbot.gesture import GestureGate, Point, classify
from deskbot.motion import CrickitServos, FakeServos, Motion, Pose
from deskbot.tracking import Box, Detection, TargetTracker
from deskbot.vision import Frame


def config():
    return Config(Axis(90, 1, -55, 55), Axis(90, -1, -15, 15), False,
                  'person.rpk', 'hand.task')


def hand_pose(kind):
    xy = [(0.5, .9)] * 21
    changes = {1:(.42,.75), 2:(.35,.68), 3:(.31,.65), 4:(.49,.65),
               5:(.44,.55), 6:(.43,.42), 7:(.42,.29), 8:(.41,.17),
               9:(.49,.53), 10:(.50,.42), 11:(.50,.54), 12:(.50,.61),
               13:(.55,.55), 14:(.56,.43), 15:(.56,.55), 16:(.55,.62),
               17:(.61,.59), 18:(.66,.47), 19:(.68,.36), 20:(.70,.27)}
    for i, value in changes.items():
        xy[i] = value
    if kind == 'love':
        xy[4] = (.18,.48)
    if kind in ('gun', 'side_gun', 'forward_gun'):
        xy[4] = (.18,.48)
        xy[18], xy[19], xy[20] = (.66,.47), (.66,.56), (.64,.64)
        xy[6], xy[7], xy[8] = (.43,.45), (.42,.39), (.41,.34 if kind == 'gun' else .17)
    if kind == 'forward_gun':
        for i in (5, 6, 7, 8):
            xy[i] = (.44, .55)
    depth = {6: -.06, 7: -.12, 8: -.18} if kind in ('gun', 'forward_gun') else {}
    return [Point(x, y, depth.get(i, 0))
            for i, (x,y) in enumerate(xy)]


class ConfigTests(unittest.TestCase):
    def test_unsafe_config_rejected(self):
        with self.assertRaises(ValueError):
            replace(config(), pan=Axis(150, 1, -55, 55)).validate()
        with self.assertRaises(ValueError):
            replace(config(), max_speed=200).validate()
        with self.assertRaises(ValueError):
            replace(config(), tilt=Axis(90, 0, -15, 15)).validate()
        with self.assertRaises(ValueError):
            replace(config(), fps=0).validate()
        with self.assertRaises(ValueError):
            replace(config(), max_hands=3).validate()

    def test_config_round_trip(self):
        path = Path('tests/_config_round_trip.toml')
        try:
            save(path, config())
            self.assertEqual(load(path), config())
        finally:
            path.unlink(missing_ok=True)

    def test_unknown_key_rejected(self):
        path = Path('tests/_config_unknown.toml')
        try:
            save(path, config())
            path.write_text(path.read_text() + '\n[extra]\nx=1\n')
            with self.assertRaises(ValueError):
                load(path)
        finally:
            path.unlink(missing_ok=True)


class MotionTests(unittest.TestCase):
    def test_clamp_and_slew(self):
        backend = FakeServos()
        motion = Motion(config(), backend)
        motion.start()
        pose = motion.step(Pose(1000, -1000), .1)
        self.assertAlmostEqual(pose.pan, 2.8)
        self.assertAlmostEqual(pose.tilt, -2.8)
        for _ in range(200):
            motion.step(Pose(1000, -1000), .1)
        self.assertEqual(motion.pose, Pose(55, -15))
        self.assertEqual(backend.angles[-1], (145, 105))
        with self.assertRaises(ValueError):
            motion.step(Pose(float('nan'), 0), .1)

    def test_both_servo_channels_release_after_first_failure(self):
        class FailingServo:
            def __init__(self, fail=False):
                self.fail = fail
                self.writes = []
            @property
            def angle(self):
                return None
            @angle.setter
            def angle(self, value):
                self.writes.append(value)
                if self.fail:
                    raise OSError('first channel failed')
        servos = CrickitServos.__new__(CrickitServos)
        servos.pan = FailingServo(fail=True)
        servos.tilt = FailingServo()
        with self.assertRaisesRegex(OSError, 'first channel failed'):
            servos.close()
        self.assertEqual(servos.pan.writes, [None])
        self.assertEqual(servos.tilt.writes, [None])


class TrackerTests(unittest.TestCase):
    def test_sticky_target_and_stale_expiry(self):
        tracker = TargetTracker(config())
        a = Detection(Box(100, 50, 150, 350), .9)
        b = Detection(Box(400, 40, 200, 390), .9)
        self.assertEqual(tracker.select([a], 0), a.box)
        self.assertEqual(tracker.select([b], .2), a.box)
        self.assertEqual(tracker.select(None, 1.0), None)
        self.assertEqual(tracker.select([b], 1.1), b.box)

    def test_aim_deadband(self):
        tracker = TargetTracker(config())
        tracker.select([Detection(Box(245, 100, 150, 350), .9)], 0)
        self.assertGreaterEqual(tracker.aim(Pose()).tilt, 0)


class GestureTests(unittest.TestCase):
    def test_geometry(self):
        self.assertEqual(classify(hand_pose('rock')), 'rock_on')
        self.assertIsNone(classify(hand_pose('love')))
        self.assertEqual(classify(hand_pose('gun')), 'finger_gun')
        self.assertEqual(classify(hand_pose('forward_gun')), 'finger_gun')
        self.assertIsNone(classify(hand_pose('side_gun')))
        for size in (.6, 1.2):
            scaled = [Point(.5 + (p.x - .5) * size,
                            .5 + (p.y - .5) * size, p.z * size)
                      for p in hand_pose('forward_gun')]
            self.assertEqual(classify(scaled), 'finger_gun')
        open_palm = hand_pose('love')
        for m, p, t in ((9,10,12), (13,14,16)):
            open_palm[t] = Point(open_palm[p].x + (open_palm[p].x - open_palm[m].x),
                                 open_palm[p].y + (open_palm[p].y - open_palm[m].y))
        self.assertIsNone(classify(open_palm))

    def test_debounce_rearm_and_cooldown(self):
        gate = GestureGate(3, 2)
        self.assertIsNone(gate.update('rock_on', 0))
        self.assertIsNone(gate.update('rock_on', .1))
        self.assertEqual(gate.update('rock_on', .2), 'rock_on')
        self.assertIsNone(gate.update('rock_on', 3))
        gate.update(None, 3.1)
        gate.update('rock_on', 3.2)
        gate.update('rock_on', 3.3)
        self.assertEqual(gate.update('rock_on', 3.4), 'rock_on')

    def test_busy_gate_does_not_consume_trigger(self):
        gate = GestureGate(3, 2)
        for t in (0, .1, .2):
            self.assertIsNone(gate.update('finger_gun', t, enabled=False))
        self.assertEqual(gate.update('finger_gun', .3), 'finger_gun')


class IntegrationTests(unittest.TestCase):
    def test_reaction_owns_motion_then_resumes(self):
        backend = FakeServos()
        motion = Motion(config(), backend)
        motion.start()
        robot = Robot(config(), motion)
        frame = Frame(None, [Detection(Box(200, 100, 200, 350), .9)], [hand_pose('rock')])
        for t in (0, .1, .2):
            robot.process(frame, t)
        self.assertEqual(robot.behavior.kind, 'rock_on')
        robot.process(frame, .4)
        self.assertNotEqual(motion.pose, Pose())
        robot.process(Frame(None, [], []), 2.0)
        self.assertIsNone(robot.behavior.kind)
        self.assertTrue(all(35 <= pan <= 145 and 75 <= tilt <= 105 for pan, tilt in backend.angles))

    def test_unrelated_hand_cannot_trigger(self):
        robot = Robot(config())
        frame = Frame(None, [Detection(Box(0, 0, 100, 300), .9)], [hand_pose('rock')])
        for t in (0, .1, .2):
            robot.process(frame, t)
        self.assertIsNone(robot.behavior.kind)

    def test_old_capture_does_not_drive_motion(self):
        motion = Motion(config(), FakeServos())
        motion.start()
        robot = Robot(config(), motion)
        old = Frame(None, [Detection(Box(500, 0, 120, 400), .9)], [], captured_at=0)
        status, _ = robot.process(old, 2)
        self.assertIn('person=no', status)
        self.assertEqual(motion.pose, Pose())

    def test_swapped_hand_order_keeps_separate_gates(self):
        robot = Robot(config())
        left = hand_pose('rock')
        right = [Point(p.x + .25, p.y, p.z) for p in hand_pose('love')]
        person = [Detection(Box(100, 0, 500, 480), .9)]
        robot.process(Frame(None, person, [left, right]), 0)
        robot.process(Frame(None, person, [right, left]), .1)
        robot.process(Frame(None, person, [left, right]), .2)
        self.assertEqual(robot.behavior.kind, 'rock_on')

    def test_hand_gap_does_not_bypass_cooldown(self):
        robot = Robot(config())
        hand = hand_pose('rock')
        person = [Detection(Box(100, 0, 500, 480), .9)]
        for t in (0, .1, .2):
            robot.process(Frame(None, person, [hand]), t)
        robot.process(Frame(None, person, []), .3)
        robot.behavior.kind = None
        for t in (.4, .5, .6):
            robot.process(Frame(None, person, [hand]), t)
        self.assertIsNone(robot.behavior.kind)

    def test_wrist_jump_does_not_bypass_shared_cooldown(self):
        robot = Robot(config())
        hand = hand_pose('rock')
        shifted = [Point(p.x + .20, p.y, p.z) for p in hand]
        person = [Detection(Box(0, 0, 640, 480), .9)]
        for t in (0, .1, .2, 1.8):
            robot.process(Frame(None, person, [hand]), t)
        for t in (1.9, 2.0, 2.1):
            robot.process(Frame(None, person, [shifted]), t)
        self.assertAlmostEqual(robot.last_reaction, .2)
        self.assertIsNone(robot.behavior.kind)

    def test_sigterm_path_closes_hardware_and_restores_handler(self):
        backend = FakeServos()
        backend.closed = False
        def close():
            backend.closed = True
        backend.close = close
        class Camera:
            def __init__(self, *_args, **_kwargs):
                self.closed = False
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                self.closed = True
            def capture(self):
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        camera = Camera()
        old_handler = signal.getsignal(signal.SIGTERM)
        with patch('deskbot.vision.CameraVision', return_value=camera), \
             patch('deskbot.motion.CrickitServos', return_value=backend):
            run(replace(config(), calibrated=True), hardware=True)
        self.assertTrue(camera.closed)
        self.assertTrue(backend.closed)
        self.assertIs(signal.getsignal(signal.SIGTERM), old_handler)

    def test_live_pulse_edit_is_not_a_calibration_command(self):
        backend = FakeServos()
        out = io.StringIO()
        with patch('deskbot.motion.CrickitServos', return_value=backend), \
             patch('builtins.input', side_effect=['ATTACH', 'pulse pan 800 2300', 'quit']), \
             contextlib.redirect_stdout(out):
            calibrate(Path('tests/_unused.toml'), config())
        self.assertIn('Unknown command', out.getvalue())
        self.assertEqual(list(backend.angles), [(90, 90)])


if __name__ == '__main__':
    unittest.main()
