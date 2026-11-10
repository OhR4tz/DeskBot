# DeskBot

DeskBot is a local pan/tilt companion for an assembled RoboBuddy. It follows one visible person and reacts to two hand poses: a small happy nod/wiggle for “rock on” and a downcast glance for a raised middle finger.

The build uses a **Raspberry Pi 5 with 2 GB RAM**, **one Raspberry Pi AI Camera (IMX500)** in the head, an **Adafruit CRICKIT HAT #3957**, and two positional MG90S servos. CRICKIT port 1 is pan; port 2 is tilt. The same camera supplies on-camera SSD person detections and RGB images for CPU hand recognition. No second camera is needed.

Start here:

1. [Prepare the microSD, connect over SSH, and install](docs/setup.md).
2. [Check and calibrate the assembled head](docs/calibration.md).
3. [Understand the code, settings, and limitations](docs/architecture.md).
4. [Read the supplied mechanical model notes](mechanical/README.md).

The initial configuration is **uncalibrated**, with narrow pan ±10° and tilt ±5° bounds. `observe` uses no servo hardware, and `run` simulates servo writes unless `--enable-servos` is explicitly supplied. Hardware running also requires a completed calibration. The intended checked range is pan ±55° and tilt ±15°; the actual safe range must be established on the assembled robot.

Before assembled calibration, use the [detached centering workflow](docs/calibration.md#before-the-first-attachment) for each servo with unknown neutral. `center-servo pan` or `center-servo tilt` commands only that unloaded axis after an explicit confirmation. Pointing an unpowered head forward does not establish electrical zero.

**Power:** use the Pi's USB-C wall supply and the CRICKIT's 5 V / 4 A barrel supply. Their rails are diode coupled through the HAT, so unplugging Pi USB-C alone does not guarantee that the Pi is off. Shut down and disconnect **both supplies** before wiring or adjusting the assembly.

This is a prototype. All 26 hardware-free tests, simulation, and preflight pass on the 2 GB Pi. Both gestures triggered once per held pose in a real-camera trial without motor commands. A short warmed sample met the requested 10 FPS; this is not a long-run performance guarantee. Detached pan centering has been checked, while tilt alignment, assembled calibration, physical tracking/reaction motion, and clearances still need validation. Gesture recognition uses heuristics and can vary with hands, viewpoint, and lighting. See the [validation details](docs/architecture.md#repository-map-and-development-checks).

Private repository: [OhR4tz/DeskBot](https://github.com/OhR4tz/DeskBot). Installation requires access to that repository.
