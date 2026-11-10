# How DeskBot works

## One camera, two inference paths

The AI Camera's IMX500 runs the packaged SSD MobileNet person detector. Picamera2 supplies that inference metadata and the corresponding RGB image from the **same head-mounted camera**. MediaPipe Hand Landmarker runs on the Pi CPU in `VIDEO` mode using that image. No second camera or cloud inference service is used at runtime.

The default 640 × 480 stream requests a maximum of 10 FPS, limited further by the camera model's inference rate. Actual throughput depends on the Pi and CPU hand inference. Four camera buffers and one detected hand are the initial 2 GB settings; either hand can be recognized. `max_hands = 2` is optional after measuring resource use.

## Tracking and reactions

The tracker initially favors a large, confident person detection, then prefers a nearby continuation of that box. It aims at the upper portion of the person box, with smoothing and an image deadband. It does not recognize an owner, identify faces, or precisely localize a face. With several people present, it can choose or eventually switch to someone else.

Missing or stale results stop fresh tracking corrections and eventually discard the target. Target loss does not start an aggressive search sweep. Hands are associated with the selected person's image region; overlapping people or hands can still confuse that spatial association.

The gesture classifier uses aspect-corrected 3D finger angles and palm-normalized hand geometry:

| Pose | Intended reaction |
| --- | --- |
| Rock on: index and little finger extended, middle/ring curled, thumb folded | About 1.5 seconds of nodding and small pan wiggles. |
| Raised middle finger: middle extended, index/ring/little curled, thumb unrestricted | About 1.3 seconds of a downcast glance and return. |

Reactions require repeated matching frames, use a global cooldown, and temporarily own motion before tracking resumes. Release the pose to rearm. The heuristic thresholds need actual hand, viewpoint, distance, and lighting tests. The “I love you” pose with an extended thumb is intended to be rejected as rock on. Status uses `rock_on` and `middle_finger` for the two reactions.

## Motion and configuration

Only `motion.py` writes servo commands. It maps world-relative pan/tilt through each axis's center and direction, clamps targets, and limits travel rate. Startup directly commands the configured centers because positional MG90S servos provide no position feedback. First electrically center each unknown servo unloaded, then index its horn with power off; see [the centering and initial-jump precautions](calibration.md#before-the-first-attachment).

`center-servo pan|tilt` requires the exact `DETACHED` acknowledgement before hardware access and commands only that axis at its configured center (default 90°, nominally 1500 microseconds). It waits for Enter, then releases that channel in cleanup. Centering and interactive calibration also handle SIGTERM and SSH hangup through cleanup and restore the previous signal handlers. Centering performs no sweep and does not arm calibration. It cannot verify that the linkage was actually detached.

Default `configs/deskbot.toml` settings include:

| Setting | Meaning |
| --- | --- |
| `calibrated = false` | Blocks hardware `run` until physical calibration is completed. |
| `[pan]`, `[tilt]` | Center, direction, checked world bounds, and pulse mapping. |
| `model`, `hand_model` | IMX500 SSD `.rpk` and downloaded MediaPipe `.task` paths. |
| `person_threshold = 0.55` | Minimum person score. |
| `deadband = 0.065` | Ignore small normalized image-center errors. |
| `pan_gain`, `tilt_gain` | Tracking correction strength. |
| `max_speed = 28.0` | Maximum commanded travel rate in degrees/second after startup. |
| `inference_timeout = 0.8` | Expire missing/old inference results. |
| `lost_timeout = 1.2` | Retain a target briefly across empty detections. |
| `gesture_frames = 3`, `gesture_cooldown = 3.0` | Matching-frame debounce and minimum seconds between reaction starts. |

Unknown configuration keys and unsafe numeric settings are rejected. Relative paths are resolved from the process's working directory, so run commands from the project root. To use another configuration, put the global option before the subcommand:

```bash
.venv/bin/deskbot --config configs/deskbot.toml observe
```

Stop the process before editing its configuration; changes are read on the next start. Follow the calibration guide for changes that affect physical motion.

## Repository map and development checks

| Path | Purpose |
| --- | --- |
| `src/deskbot/cli.py` | Commands, simulation, interactive calibration. |
| `src/deskbot/vision.py` | Picamera2, IMX500 SSD parsing, MediaPipe landmarks. |
| `src/deskbot/tracking.py` | Person selection and image-to-head corrections. |
| `src/deskbot/gesture.py` | Hand geometry and trigger debounce. |
| `src/deskbot/behavior.py` | Timed reaction poses. |
| `src/deskbot/app.py` | Tracking/reaction orchestration and shutdown. |
| `src/deskbot/config.py`, `motion.py` | Configuration validation and bounded servo output. |
| `scripts/` | Pi installer and nonmovement preflight. |
| `deploy/` | Manually installed systemd template. |
| `tests/` | Hardware-free unit and integration checks. |

Python 3.11 or newer is required. Base installation has no third-party dependencies, so simulation and core tests can run on a development computer:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
deskbot simulate
```

The current 26-test hardware-free suite passes. Initial Windows development checks used Python 3.13.11 and also covered simulation and Python compilation. A blank-image API smoke check passed with MediaPipe 1.2.2, NumPy 2.3.5, and the official hand model; the package build and Bash syntax were also checked.

The `pi` extra includes Adafruit CRICKIT and, specifically on Linux/aarch64, `Adafruit-Blinka-Raspberry-Pi-PWM>=1.0.2`, which supplies the native PWM dependency required by the current Blinka stack. The installer also adds MediaPipe and OS-managed Picamera2, OpenCV, IMX500 support, and camera models. Models are installed/downloaded separately.

Preflight imports the camera, MediaPipe, `pwmio`, and `adafruit_motor.servo` modules. It finds the CRICKIT package without importing its board singleton or opening board I2C, so the CRICKIT barrel stays unplugged during camera checks. It requires Picamera2 to enumerate an IMX500 and fails clearly otherwise. A present I2C device and installed driver do not establish communication with the CRICKIT; that is checked later during powered, unloaded servo centering.

All 26 hardware-free tests, simulation, and the updated preflight passed on the actual Pi 5 Model B Rev 1.1 with 2 GB RAM and 64-bit Trixie. As of 2026-11-09, both `rpicam-hello` and Picamera2 enumerate the IMX500 after its ribbon was connected correctly. The installed stack is Picamera2 0.3.38, MediaPipe 1.2.2, NumPy 2.2.4, CRICKIT 2.3.24, Blinka 10.1.0, and native PWM 1.0.2.

A short camera inference sample on that Pi used 640 × 480, `fps = 10`, and `max_hands = 1`, with no servo actions. Five warm-up captures were excluded:

| Measurement | Sample result |
| --- | --- |
| Captures and elapsed time | 201 frames in 20.1 seconds: 10.00 FPS |
| Frames with person detections | 201 |
| Frames with hand detections | 32 |
| Peak process resident memory | 242.1 MiB |
| Temperature at check | 40.6°C |
| `vcgencmd get_throttled` | `0x0` |
| Available system RAM / swap use | About 1.5 GiB available / no swap used |

This is one short warmed sample, not a guarantee of sustained performance or gesture accuracy. An earlier cold run waited about 33 seconds for its first capture; startup delay should be considered separately from warmed throughput.

A separate 55-second real-camera trial classified `middle_finger` in 192 frames and `rock_on` in 156 frames, with exactly one reaction start for each held pose. No motors were commanded during that trial. Both gesture triggers were therefore verified in that session; broader hand, viewpoint, and lighting reliability still needs testing.

After the CRICKIT barrel supply was connected, the board responded at I2C address `0x49`. The first assembled center attempt caused a large unexpected rightward pan and cable binding; barrel power was cut and calibration stopped. That movement does not establish a software offset or a safe travel range.

In recovery, pan was mechanically unloaded and `center-servo pan` commanded port 1 only. The servo settled with the head stationary, as confirmed by the operator, then was released and powered off for horn re-indexing. Tilt alignment, assembled calibration, physical tracking/reaction motion, and clearance remain unvalidated.

Implementation references: [Raspberry Pi AI Camera](https://www.raspberrypi.com/documentation/accessories/ai-camera.html), [official IMX500 object-detection example](https://github.com/raspberrypi/picamera2-examples/blob/main/examples/imx500/imx500_object_detection_demo.py), [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker), and [MediaPipe Python setup](https://developers.google.com/edge/mediapipe/solutions/setup_python). The target OS comes from [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/).
