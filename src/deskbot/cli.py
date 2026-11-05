"""Explicit motion gate, readable dry run and small-step manual calibration."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys
import time

from .config import Config, load, save, with_axis
from .motion import Motion, Pose, FakeServos


def calibrate(path: Path, config: Config) -> None:
    print("Manual calibration of the ASSEMBLED head. Pan port 1, tilt port 2.")
    print("Pi powered separately; CRICKIT DC jack 5 V/4 A. Keep fingers and cable clear.")
    print("Power servos, place head near neutral by hand with power OFF first.")
    print("Attaching commands the configured center; disconnect power if it binds.")
    print("Start at narrow bounds, jog in <=2 degree steps, then expand ranges gradually.")
    print("Goal after clearance checks: pan -55..55, tilt -15..15 world degrees.")
    if input("Type ATTACH to energize both servos: ").strip() != "ATTACH":
        return
    from .motion import CrickitServos
    motion = Motion(config, CrickitServos(config))
    visited = {name: [0.0, 0.0] for name in ("pan", "tilt")}
    try:
        motion.start()
        print("Commands: pan +2 | tilt -2 | neutral | center pan 91 | direction pan -1")
        print("          range pan -20 20 | show | save | arm | quit")
        print("Edit pulse_min/pulse_max in TOML only with both supplies OFF; then recalibrate.")
        while True:
            parts = input("calibrate> ").lower().split()
            if not parts:
                continue
            command = parts[0]
            try:
                if command == "quit":
                    break
                if command == "show":
                    print(f"pose={motion.pose} pan={config.pan} tilt={config.tilt} calibrated={config.calibrated}")
                elif command == "neutral" and len(parts) == 1:
                    _move(motion, Pose())
                elif command in ("pan", "tilt") and len(parts) == 2:
                    delta = float(parts[1])
                    if not 0 < abs(delta) <= 2:
                        raise ValueError("jog size must be >0 and <=2 degrees")
                    axis = getattr(config, command)
                    old = getattr(motion.pose, command)
                    wanted = old + delta
                    if wanted != axis.clamp(wanted):
                        raise ValueError("jog exceeds configured range; expand it only after clearance check")
                    _move(motion, replace(motion.pose, **{command: wanted}))
                    visited[command][0] = min(visited[command][0], wanted)
                    visited[command][1] = max(visited[command][1], wanted)
                elif command in ("center", "direction", "range"):
                    if len(parts) < 3 or parts[1] not in ("pan", "tilt"):
                        raise ValueError("specify pan or tilt and value(s)")
                    name = parts[1]
                    if command in ("center", "direction") and motion.pose != Pose():
                        raise ValueError("return to neutral before changing center or direction")
                    if command == "center" and len(parts) == 3:
                        value = float(parts[2])
                        if abs(value - getattr(config, name).center) > 2:
                            raise ValueError("change center by at most 2 degrees at a time")
                        config = with_axis(config, name, center=value)
                    elif command == "direction" and len(parts) == 3:
                        config = with_axis(config, name, direction=int(parts[2]))
                    elif command == "range" and len(parts) == 4:
                        old = getattr(config, name)
                        low, high = float(parts[2]), float(parts[3])
                        if abs(low - old.minimum) > 5 or abs(high - old.maximum) > 5:
                            raise ValueError("expand or contract each end by at most 5 degrees per edit")
                        if not low <= getattr(motion.pose, name) <= high:
                            raise ValueError("return inside new range before contracting it")
                        config = with_axis(config, name, minimum=low, maximum=high)
                    else:
                        raise ValueError("invalid command syntax")
                    motion.config = config
                    if command in ("center", "direction"):
                        visited[name] = [0.0, 0.0]
                    if command in ("center", "direction"):
                        motion.servos.write(config.pan.servo_angle(0), config.tilt.servo_angle(0))
                    print(f"{name}: {getattr(config, name)}; calibration disarmed")
                elif command == "save" and len(parts) == 1:
                    save(path, config)
                    print(f"saved {path}")
                elif command == "arm" and len(parts) == 1:
                    if motion.pose != Pose():
                        raise ValueError("return to neutral first")
                    for name in ("pan", "tilt"):
                        axis = getattr(config, name)
                        if visited[name][0] > axis.minimum + 1 or visited[name][1] < axis.maximum - 1:
                            raise ValueError(f"jog {name} to both configured ends in this session before arming")
                    if input("Both axes cleared and camera ribbon free? Type CALIBRATED: ").strip() != "CALIBRATED":
                        continue
                    config = replace(config, calibrated=True)
                    save(path, config)
                    print(f"armed and saved {path}")
                else:
                    print("Unknown command; type show or quit")
            except (ValueError, TypeError) as error:
                print(f"Rejected: {error}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        motion.close()


def _move(motion: Motion, pose: Pose) -> None:
    while abs(motion.pose.pan - pose.pan) > 0.01 or abs(motion.pose.tilt - pose.tilt) > 0.01:
        motion.step(pose, 0.05)
        time.sleep(0.05)
    print(f"pose={motion.pose}")


def simulate(config: Config) -> None:
    from .app import Robot
    from .tracking import Box, Detection
    from .vision import Frame
    motion = Motion(config, FakeServos())
    motion.start()
    robot = Robot(config, motion)
    try:
        for index in range(80):
            x = 80 + 4 * index if index < 40 else 240
            frame = Frame(None, [Detection(Box(x, 80, 150, 340), 0.9)], [])
            status, _ = robot.process(frame, index * 0.05)
            if index % 10 == 0:
                print(f"t={index * 0.05:.1f} {status} pose={motion.pose}")
    finally:
        motion.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-camera local desk robot")
    parser.add_argument("--config", type=Path, default=Path("configs/deskbot.toml"))
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("simulate", help="hardware-free fake-person tracking")
    subs.add_parser("observe", help="camera and gesture status, no servo hardware")
    run_cmd = subs.add_parser("run", help="camera tracking with simulated servo writes by default")
    run_cmd.add_argument("--enable-servos", action="store_true", help="energize CRICKIT after calibration")
    run_cmd.add_argument("--preview", action="store_true", help="show camera preview on a desktop")
    observe_cmd = subs.choices["observe"]
    observe_cmd.add_argument("--preview", action="store_true")
    subs.add_parser("calibrate", help="interactive small-step assembled-head calibration")
    args = parser.parse_args(argv)
    try:
        config = load(args.config)
        if args.command == "simulate":
            simulate(config)
        elif args.command == "calibrate":
            calibrate(args.config, config)
        else:
            from .app import run
            run(config, hardware=getattr(args, "enable_servos", False),
                preview=args.preview, observe_only=args.command == "observe")
    except (ValueError, FileNotFoundError, ImportError, RuntimeError) as error:
        print(f"DeskBot: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
