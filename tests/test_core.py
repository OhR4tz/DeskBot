import unittest
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path
import contextlib
import io
import signal
import sys
from types import SimpleNamespace

from deskbot.app import Robot, run
from deskbot.behavior import Behavior
from deskbot.cli import calibrate, center_servo
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
    if kind in ('love', 'old_gun', 'middle_thumb_out', 'open'):
        xy[4] = (.18,.48)
    if kind in ('middle', 'middle_thumb_out', 'fist'):
        xy[7], xy[8] = (.44,.49), (.44,.59)
        xy[18], xy[19], xy[20] = (.66,.47), (.66,.56), (.64,.64)
    if kind in ('middle', 'middle_thumb_out'):
        xy[10], xy[11], xy[12] = (.49,.40), (.49,.26), (.49,.12)
    if kind == 'old_gun':
        for i in (5, 6, 7, 8):
            xy[i] = (.44, .55)
        xy[18], xy[19], xy[20] = (.66,.47), (.66,.56), (.64,.64)
    if kind == 'index_only':
        xy[18], xy[19], xy[20] = (.66,.47), (.66,.56), (.64,.64)
    if kind == 'peace':
        xy[10], xy[11], xy[12] = (.49,.40), (.49,.26), (.49,.12)
        xy[18], xy[19], xy[20] = (.66,.47), (.66,.56), (.64,.64)
    if kind == 'open':
        for m, p, dip, tip in ((9,10,11,12), (13,14,15,16)):
            xy[dip] = (xy[p][0] + (xy[p][0] - xy[m][0]),
                       xy[p][1] + (xy[p][1] - xy[m][1]))
            xy[tip] = (xy[p][0] + 2 * (xy[p][0] - xy[m][0]),
                       xy[p][1] + 2 * (xy[p][1] - xy[m][1]))
    depth = {6: -.06, 7: -.12, 8: -.18} if kind == 'old_gun' else {}
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
        replace(config(), tilt=Axis(90, -1, -60, 60)).validate()
        replace(config(), pan=Axis(97, 1, -70, 70)).validate()
        with self.assertRaises(ValueError):
            replace(config(), pan=Axis(97, 1, -70, 71)).validate()
        with self.assertRaises(ValueError):
            replace(config(), pan=Axis(111, 1, -70, 70)).validate()
        with self.assertRaises(ValueError):
            replace(config(), tilt=Axis(90, -1, -61, 60)).validate()
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


class CenterServoTests(unittest.TestCase):
    class Servo:
        def __init__(self):
            self.writes = []
            self.pulse_range = None
            self.actuation_range = None

        @property
        def angle(self):
            return self.writes[-1] if self.writes else None

        @angle.setter
        def angle(self, value):
            self.writes.append(value)

        def set_pulse_width_range(self, *, min_pulse, max_pulse):
            self.pulse_range = (min_pulse, max_pulse)

    class Board:
        def __init__(self):
            self.pan = CenterServoTests.Servo()
            self.tilt = CenterServoTests.Servo()
            self.accesses = []

        @property
        def servo_1(self):
            self.accesses.append('servo_1')
            return self.pan

        @property
        def servo_2(self):
            self.accesses.append('servo_2')
            return self.tilt

    def test_only_selected_channel_is_initialized_centered_and_released(self):
        cfg = replace(config(), tilt=Axis(96, -1, -15, 15))
        for name, port, center in (('pan', 'servo_1', 90), ('tilt', 'servo_2', 96)):
            with self.subTest(name=name):
                board = self.Board()
                with patch.dict(sys.modules, {'adafruit_crickit': SimpleNamespace(crickit=board)}), \
                     patch('builtins.input', side_effect=['DETACHED', '']), \
                     contextlib.redirect_stdout(io.StringIO()):
                    center_servo(cfg, name)
                selected = board.pan if name == 'pan' else board.tilt
                other = board.tilt if name == 'pan' else board.pan
                self.assertEqual(board.accesses, [port])
                self.assertEqual(selected.writes, [center, None])
                self.assertEqual(selected.pulse_range, (750, 2250))
                self.assertEqual(selected.actuation_range, 180)
                self.assertEqual(other.writes, [])
                self.assertIsNone(other.pulse_range)

    def test_cancel_does_not_access_hardware(self):
        for response in ('no', EOFError):
            with self.subTest(response=response), \
                 patch('deskbot.motion.CrickitSingleServo') as hardware, \
                 patch('builtins.input', side_effect=[response]), \
                 contextlib.redirect_stdout(io.StringIO()):
                center_servo(config(), 'pan')
                hardware.assert_not_called()

    def test_eof_after_center_releases_selected_channel(self):
        board = self.Board()
        with patch.dict(sys.modules, {'adafruit_crickit': SimpleNamespace(crickit=board)}), \
             patch('builtins.input', side_effect=['DETACHED', EOFError]), \
             contextlib.redirect_stdout(io.StringIO()):
            center_servo(config(), 'tilt')
        self.assertEqual(board.accesses, ['servo_2'])
        self.assertEqual(board.tilt.writes, [90, None])
        self.assertEqual(board.pan.writes, [])

    def test_lost_board_during_release_has_clear_error(self):
        class LostBoardServo(self.Servo):
            @self.Servo.angle.setter
            def angle(self, value):
                self.writes.append(value)
                if value is None:
                    raise OSError('I2C missing')
        board = self.Board()
        board.pan = LostBoardServo()
        prior_term = signal.getsignal(signal.SIGTERM)
        prior_hup = signal.getsignal(signal.SIGHUP) if hasattr(signal, 'SIGHUP') else None
        with patch.dict(sys.modules, {'adafruit_crickit': SimpleNamespace(crickit=board)}), \
             patch('builtins.input', side_effect=['DETACHED', '']), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'disconnect CRICKIT barrel power'):
                center_servo(config(), 'pan')
        self.assertEqual(board.pan.writes, [90, None])
        self.assertEqual(board.tilt.writes, [])
        self.assertIs(signal.getsignal(signal.SIGTERM), prior_term)
        if prior_hup is not None:
            self.assertIs(signal.getsignal(signal.SIGHUP), prior_hup)

    def test_shutdown_signals_release_only_selected_servo_and_restore_handlers(self):
        cases = [(signal.SIGTERM, 'pan')]
        if hasattr(signal, 'SIGHUP'):
            cases.append((signal.SIGHUP, 'tilt'))
        for signum, name in cases:
            with self.subTest(signum=signum, name=name):
                board = self.Board()
                prior = signal.getsignal(signum)
                calls = 0
                def reply(_prompt):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return 'DETACHED'
                    signal.getsignal(signum)(signum, None)
                with patch.dict(sys.modules, {'adafruit_crickit': SimpleNamespace(crickit=board)}), \
                     patch('builtins.input', side_effect=reply), \
                     contextlib.redirect_stdout(io.StringIO()):
                    center_servo(config(), name)
                selected = board.pan if name == 'pan' else board.tilt
                other = board.tilt if name == 'pan' else board.pan
                self.assertEqual(selected.writes, [90, None])
                self.assertEqual(other.writes, [])
                self.assertIs(signal.getsignal(signum), prior)

    def test_calibration_shutdown_signal_uses_existing_cleanup(self):
        backend = FakeServos()
        backend.closed = False
        def close():
            backend.closed = True
        backend.close = close
        signum = signal.SIGHUP if hasattr(signal, 'SIGHUP') else signal.SIGTERM
        prior = signal.getsignal(signum)
        calls = 0
        def reply(_prompt):
            nonlocal calls
            calls += 1
            if calls == 1:
                return 'ATTACH'
            signal.getsignal(signum)(signum, None)
        with patch('deskbot.motion.CrickitServos', return_value=backend), \
             patch('builtins.input', side_effect=reply), \
             contextlib.redirect_stdout(io.StringIO()):
            calibrate(Path('tests/_unused.toml'), config())
        self.assertTrue(backend.closed)
        self.assertEqual(list(backend.angles), [(90, 90)])
        self.assertIs(signal.getsignal(signum), prior)


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

    def test_pan_tracks_image_side_with_positive_pan_turning_left(self):
        cfg = config()
        for x, expected_sign in ((80, 1), (460, -1)):
            with self.subTest(x=x):
                tracker = TargetTracker(cfg)
                tracker.select([Detection(Box(x, 100, 100, 350), .9)], 0)
                goal = tracker.aim(Pose())
                self.assertGreater(goal.pan * expected_sign, 0)
                servo_delta = cfg.pan.servo_angle(goal.pan) - cfg.pan.servo_angle(0)
                self.assertGreater(servo_delta * cfg.pan.direction * expected_sign, 0)


class GestureTests(unittest.TestCase):
    def test_rock_on_and_middle_finger_geometry(self):
        self.assertEqual(classify(hand_pose('rock')), 'rock_on')
        self.assertEqual(classify(hand_pose('middle')), 'middle_finger')
        self.assertEqual(classify(hand_pose('middle_thumb_out')), 'middle_finger')
        for size in (.6, 1.2):
            scaled = [Point(.5 + (p.x - .5) * size,
                            .5 + (p.y - .5) * size, p.z * size)
                      for p in hand_pose('middle')]
            mirrored = [Point(1 - p.x, p.y, p.z) for p in scaled]
            self.assertEqual(classify(scaled), 'middle_finger')
            self.assertEqual(classify(mirrored), 'middle_finger')

    def test_other_hand_poses_do_not_trigger(self):
        self.assertIsNone(classify(hand_pose('love')))
        for kind in ('fist', 'open', 'index_only', 'old_gun', 'peace'):
            with self.subTest(kind=kind):
                self.assertIsNone(classify(hand_pose(kind)))

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
            self.assertIsNone(gate.update('middle_finger', t, enabled=False))
        self.assertEqual(gate.update('middle_finger', .3), 'middle_finger')


class IntegrationTests(unittest.TestCase):
    def test_full_downcast_reaches_limit_holds_and_returns_at_slow_frame_rates(self):
        cfg = replace(config(), tilt=Axis(83, 1, -30, 40), max_speed=60)
        for interval in (0.1, 0.5):
            with self.subTest(interval=interval):
                motion = Motion(cfg, FakeServos())
                motion.start()
                origin = Pose(12, 40)
                motion.pose = origin
                behavior = Behavior(cfg)
                behavior.trigger('middle_finger', 0, origin)
                at_bottom = []
                for step in range(200):
                    now = step * interval
                    goal = behavior.pose(now, origin, motion.pose)
                    motion.step(goal, interval)
                    if motion.pose.tilt == cfg.tilt.minimum:
                        at_bottom.append(now)
                    if behavior.kind is None:
                        break
                self.assertIsNone(behavior.kind)
                self.assertGreaterEqual(at_bottom[-1] - at_bottom[0], 0.8)
                self.assertEqual(motion.pose, origin)
                self.assertTrue(all(cfg.tilt.minimum <= tilt - cfg.tilt.center <= cfg.tilt.maximum
                                    for _, tilt in motion.servos.angles))

    def test_downcast_continues_after_looking_down_loses_person(self):
        cfg = replace(config(), tilt=Axis(83, 1, -30, 40), max_speed=60)
        motion = Motion(cfg, FakeServos())
        motion.start()
        robot = Robot(cfg, motion)
        origin = Pose(0, 40)
        motion.pose = origin
        robot.behavior.trigger('middle_finger', 0, origin)
        lowest = origin.tilt
        for step in range(100):
            robot.process(Frame(None, [], []), step / 10)
            lowest = min(lowest, motion.pose.tilt)
            if robot.behavior.kind is None:
                break
        self.assertEqual(lowest, cfg.tilt.minimum)
        self.assertIsNone(robot.behavior.kind)
        self.assertEqual(motion.pose, origin)

    def test_middle_finger_downcast_resumes_tracking_and_rearms(self):
        cfg = config()
        backend = FakeServos()
        motion = Motion(cfg, backend)
        motion.start()
        robot = Robot(cfg, motion)
        person = [Detection(Box(220, 100, 200, 350), .9)]
        held = Frame(None, person, [hand_pose('middle')])
        for t in (0, .1, .2):
            robot.process(held, t)
        self.assertEqual(robot.behavior.kind, 'middle_finger')
        origin = robot.behavior.origin
        _, downcast = robot.process(held, .3)
        self.assertEqual(downcast.tilt, cfg.tilt.minimum)
        self.assertLess(motion.pose.tilt, origin.tilt)
        for step in range(4, 37):
            _, resumed = robot.process(held, step / 10)
        self.assertIsNone(robot.behavior.kind)
        self.assertEqual(resumed, robot.target)
        self.assertIsNone(robot.behavior.kind)
        self.assertAlmostEqual(robot.last_reaction, .2)
        robot.process(Frame(None, person, []), 3.7)
        for t in (3.8, 3.9, 4.0):
            robot.process(held, t)
        self.assertEqual(robot.behavior.kind, 'middle_finger')
        self.assertAlmostEqual(robot.last_reaction, 4.0)
        self.assertTrue(all(35 <= pan <= 145 and 75 <= tilt <= 105
                            for pan, tilt in backend.angles))

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
