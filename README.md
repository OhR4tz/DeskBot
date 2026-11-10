# DeskBot

DeskBot is a local pan/tilt companion for an assembled RoboBuddy. It centers a visible face and uses person detections as a fallback. Rock-on triggers three nods, thumbs-down triggers a happy nod/wiggle, thumbs-up triggers a moderate head circle, and a raised middle finger triggers a look to the calibrated downward tilt limit.

The build uses a **Raspberry Pi 5 with 2 GB RAM**, **one Raspberry Pi AI Camera (IMX500)** in the head, an **Adafruit CRICKIT HAT #3957**, and two positional MG90S servos. CRICKIT port 1 is pan; port 2 is tilt. The same camera supplies on-camera SSD person detections and RGB images for CPU face detection and hand recognition. No second camera is needed.

Start here:

1. [Prepare the microSD, connect over SSH, and install](docs/setup.md).
2. [Check and calibrate the assembled head](docs/calibration.md).
3. [Understand the code, settings, and limitations](docs/architecture.md).
4. [Read the supplied mechanical model notes](mechanical/README.md).

The initial configuration is **uncalibrated**, with narrow pan ±10° and tilt ±5° bounds. `observe` uses no servo hardware, and `run` simulates servo writes unless `--enable-servos` is explicitly supplied. Hardware running also requires a completed calibration. Configurable ceilings are pan ±70° and tilt ±60°, with servo angles constrained to 0–180°. The actual safe range must be established progressively on the assembled robot.

Before assembled calibration, use the [detached centering workflow](docs/calibration.md#before-the-first-attachment) for each servo with unknown neutral. `center-servo pan` or `center-servo tilt` commands only that unloaded axis after an explicit confirmation. Pointing an unpowered head forward does not establish electrical zero.

**Power:** use the Pi's USB-C wall supply and the CRICKIT's 5 V / 4 A barrel supply. Their rails are diode coupled through the HAT, so unplugging Pi USB-C alone does not guarantee that the Pi is off. Shut down and disconnect **both supplies** before wiring or adjusting the assembly.

This is a prototype. The hardware-free suite contains 40 tests. On the assembled robot, the operator confirmed pan ±70°, tilt −30°/+40°, all four corners clear, and the final face-tracking tuning. All four gestures appeared in motor-enabled trial logs, and the operator confirmed the revised rock-on nods, thumbs-down wiggle, and thumbs-up circle work. Gesture recognition uses heuristics and can vary with hands, viewpoint, and lighting. See the [validation details](docs/architecture.md#repository-map-and-development-checks).

Private repository: [OhR4tz/DeskBot](https://github.com/OhR4tz/DeskBot). Installation requires access to that repository.

The configured robot runs automatically through `deskbot.service`; startup was verified after a reboot. See [service controls](docs/setup.md#8-optional-start-with-systemd) to stop, restart, or disable it. Calibration and tuning live in the Pi's `configs/deskbot.toml`; syncing source must preserve that robot-specific file.
