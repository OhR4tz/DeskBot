# How DeskBot works

## One camera, three inference paths

The AI Camera's IMX500 runs the packaged SSD MobileNet person detector. Picamera2 supplies that inference metadata and the corresponding RGB image from the **same head-mounted camera**. MediaPipe Face Detector and Hand Landmarker run on the Pi CPU in `VIDEO` mode using that image and a shared monotonically increasing frame timestamp. The installer downloads the BlazeFace short-range face model as well as the hand model. No second camera or cloud inference service is used at runtime.

The default 640 × 480 stream requests 10 FPS; the tuned robot profile requests 20 FPS. CPU face/hand updates use camera frames independently of the IMX500 person model's inference cadence. Actual throughput depends on the Pi and CPU inference. Four camera buffers and one detected hand are the initial 2 GB settings; either hand can be recognized. `max_hands = 2` is optional after measuring resource use.

## Tracking and reactions

The person tracker initially favors a large, confident detection, then prefers a nearby continuation of that box. A separate face tracker aims at the center of a detected face, preferring faces inside the selected person's region. Face tracking can continue when a close view contains a face without a person detection. It holds briefly across missing faces, then falls back to the upper portion of the person box. Face detection locates a face; it does not recognize an owner or identify a person. With several people present, it can choose or eventually switch to someone else.

Both aim coordinates use an adaptive filter: larger changes receive weight 0.75 to reduce following delay, while changes within 10 pixels receive weight 0.2 to damp jitter. Corrections use elapsed time, a continuous small center deadband, and a 120°/s² limit on changes in tracking velocity. This eases direction changes while continuing to correct visible centering errors. Gesture motion bypasses the tracking velocity ramp and remains subject to the shared servo speed and travel limits. Status includes measured `fps`, `face`, `aim`, and face-center pixel error; preview draws the face box and frame center.

Missing or stale results stop fresh tracking corrections and eventually discard the target. Target loss does not start an aggressive search sweep. Hands are associated with the selected person's image region; overlapping people or hands can still confuse that spatial association.

The gesture classifier uses aspect-corrected 3D finger angles and palm-normalized hand geometry:

| Pose | Intended reaction |
| --- | --- |
| Rock on: index and little finger extended, middle/ring curled, thumb folded | Three tilt-only nods with 15° strokes, returning to the triggering pose after each nod. The first stroke reverses near the lower limit. |
| Thumbs-down: four fingers curled, thumb straight and pointing down in the image | The original rock-on routine: about 1.5 seconds of small happy nods and pan wiggles. |
| Thumbs-up: four fingers curled, thumb straight and pointing up in the image | One elliptical head circle, up to 24° wide and 20° tall, then return to the triggering pose. The circle shifts inward near limits, retaining a margin. |
| Raised middle finger: middle extended, index/ring/little curled, thumb unrestricted | Move to the configured downward tilt limit, hold for 0.8 seconds after commanded arrival, then return to the triggering pose before tracking resumes. |

Reactions require repeated matching frames, use a global cooldown, and temporarily own motion before tracking resumes. Release the pose to rearm. The heuristic thresholds need actual hand, viewpoint, distance, and lighting tests. The “I love you” pose with an extended thumb is intended to be rejected as rock on. Status uses `rock_on`, `thumbs_down`, `thumbs_up`, and `middle_finger`. All four gestures reuse the same hand landmarks; no additional model is needed. Nod and circle waypoints wait for commanded arrival before advancing, so slow frame rates do not skip the strokes.

The downward reaction waits for the slew-limited commanded pose before starting its hold and return. This is command progress, not measured servo position: MG90S servos provide no feedback. A reaction already underway finishes even if looking away temporarily loses the person detection.

## Motion and configuration

Only `motion.py` writes servo commands. It maps world-relative pan/tilt through each axis's center and direction, clamps targets, and limits travel rate. Startup directly commands the configured centers because positional MG90S servos provide no position feedback. First electrically center each unknown servo unloaded, then index its horn with power off; see [the centering and initial-jump precautions](calibration.md#before-the-first-attachment).

Configurable ceilings are pan ±70° and tilt ±60°. Shipped bounds remain pan ±10° and tilt ±5°, and the existing jog, range-edit, and speed guards remain in place. Accepted bounds do not establish physical clearance. Positive world pan points toward the robot's own left; positive tilt points up.

`center-servo pan|tilt` requires the exact `DETACHED` acknowledgement before hardware access and commands only that axis at its configured center (default 90°, nominally 1500 microseconds). It waits for Enter, then releases that channel in cleanup. Centering and interactive calibration also handle SIGTERM and SSH hangup through cleanup and restore the previous signal handlers. Centering performs no sweep and does not arm calibration. It cannot verify that the linkage was actually detached.

Default `configs/deskbot.toml` settings include:

| Setting | Meaning |
| --- | --- |
| `calibrated = false` | Blocks hardware `run` until physical calibration is completed. |
| `[pan]`, `[tilt]` | Center, direction, checked world bounds, and pulse mapping. |
| `model`, `hand_model`, `face_model` | IMX500 SSD `.rpk`, downloaded hand `.task`, and face `.tflite` paths. |
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

The current 40-test hardware-free suite includes face priority and centering direction, stale face rejection, face/person association, vertical smoothing and velocity easing, center jitter rejection, gesture ownership, full downward travel and hold at reduced frame rates, and reaction completion after target loss. It also checks mirrored/scaled thumbs-up/down landmarks, three completed tilt-only nods, circles near travel limits, preservation of the original wiggle routine, and held-pose debounce. Initial Windows development checks used Python 3.13.11 and also covered simulation and Python compilation. A blank-image API smoke check passed with MediaPipe 1.2.2, NumPy 2.3.5, and the official hand model; the package build and Bash syntax were also checked.

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

In recovery, both servos were electrically centered unloaded and their horns re-indexed. On 2026-11-09, the operator confirmed straight-ahead pan center 97°, level tilt center 83°, both directions +1, pan −70°/+70°, tilt −30°/+40°, and clearance at all four combined corners. Pulse limits remain 750–2250 microseconds. The calibration tool visited both endpoints of both axes and saved `calibrated = true` after the operator's confirmation. These values apply to this assembled robot, not to another horn indexing or cable routing.

A 90-second motor-enabled trial followed that calibration. The operator confirmed correct tracking direction, and the log recorded both `middle_finger` and `rock_on` reactions. The timed run stopped automatically; the health check reported 51°C and `throttled=0x0`. After feedback about twitching and lag, face centering gained adaptive smoothing, tracking velocity easing, and a 20 FPS camera target. The operator described gains 1.0/0.8 as almost perfect and requested a small speed increase. The final saved profile uses `pan_gain = 1.1`, `tilt_gain = 0.88`, `deadband = 0.025`, `fps = 20`, and `max_speed = 60.0`, preserving the checked travel limits. Shipped defaults remain conservative. Runtime status measured approximately 10–20 FPS during the preceding 20 FPS trial, depending on inference workload. A later health check reported 64.8°C and `throttled=0x0`.

A camera-only check with person, face, and hand inference enabled captured 150 frames in 15.00 seconds (10 FPS), with face detections in all 150 frames and peak process resident memory of 249.7 MiB. This is a short sample, not a sustained performance guarantee. Face integration follows the [MediaPipe Face Detector documentation](https://developers.google.com/edge/mediapipe/solutions/vision/face_detector?tab=Python).

Implementation references: [Raspberry Pi AI Camera](https://www.raspberrypi.com/documentation/accessories/ai-camera.html), [official IMX500 object-detection example](https://github.com/raspberrypi/picamera2-examples/blob/main/examples/imx500/imx500_object_detection_demo.py), [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker), and [MediaPipe Python setup](https://developers.google.com/edge/mediapipe/solutions/setup_python). The target OS comes from [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/).
