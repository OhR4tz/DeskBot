# DeskBot

DeskBot is a local pan/tilt companion for an assembled RoboBuddy. It follows one visible person and reacts to two hand poses: a small happy nod/wiggle for “rock on” and a downcast glance for a finger gun aimed toward the camera.

The build uses a **Raspberry Pi 5 with 2 GB RAM**, **one Raspberry Pi AI Camera (IMX500)** in the head, an **Adafruit CRICKIT HAT #3957**, and two positional MG90S servos. CRICKIT port 1 is pan; port 2 is tilt. The same camera supplies on-camera SSD person detections and RGB images for CPU hand recognition. No second camera is needed.

Start here:

1. [Prepare the microSD, connect over SSH, and install](docs/setup.md).
2. [Check and calibrate the assembled head](docs/calibration.md).
3. [Understand the code, settings, and limitations](docs/architecture.md).
4. [Read the supplied mechanical model notes](mechanical/README.md).

The initial configuration is **uncalibrated**, with narrow pan ±10° and tilt ±5° bounds. `observe` uses no servo hardware, and `run` simulates servo writes unless `--enable-servos` is explicitly supplied. Hardware running also requires a completed calibration. The intended checked range is pan ±55° and tilt ±15°; the actual safe range must be established on the assembled robot.

**Power:** use the Pi's USB-C wall supply and the CRICKIT's 5 V / 4 A barrel supply. Their rails are diode coupled through the HAT, so unplugging Pi USB-C alone does not guarantee that the Pi is off. Shut down and disconnect **both supplies** before wiring or adjusting the assembly.

This is a prototype. Hardware-free checks and a MediaPipe API smoke check have been run on a development computer. The Pi camera, real servos, assembled clearances, and 2 GB performance still need physical validation. Gesture recognition uses heuristics and needs testing with real hands and lighting.

Private repository: [OhR4tz/DeskBot](https://github.com/OhR4tz/DeskBot). Installation requires access to that repository.
