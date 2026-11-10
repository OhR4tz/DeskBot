# Set up DeskBot

Follow these steps in order. Leave the CRICKIT barrel supply disconnected until the calibration guide asks for it. All robot commands below run from the `DeskBot` directory on the Pi.

## 1. Prepare the microSD on your computer

Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) and select:

- Device: **Raspberry Pi 5**.
- OS: **Raspberry Pi OS Lite (64-bit), Trixie**. Lite has no graphical desktop and suits the 2 GB Pi. The installer requires 64-bit Trixie.
- Storage: the robot's microSD. Writing the image erases the selected storage; check that it is the intended card.

In Imager's customization, set hostname `deskbot`, choose your own username and password or SSH key, configure Wi-Fi and its country, and enable SSH. Save the username you chose; there is no assumed `pi` account or default password. Raspberry Pi Connect is not required and can stay off.

Write the card, wait for verification, eject it, and insert it into the Pi.

## 2. Check the unpowered wiring, then boot

With **both supplies disconnected**, check:

- The single AI Camera is connected with a Pi 5 compatible ribbon cable, correctly oriented and fully latched at both ends. Follow the [official AI Camera connection instructions](https://www.raspberrypi.com/documentation/accessories/ai-camera.html).
- The CRICKIT HAT is correctly seated on the Pi GPIO header.
- Pan MG90S is on CRICKIT **servo port 1**; tilt MG90S is on **servo port 2**. Match signal, 5 V, and ground to the board labels and your servo's verified wiring; do not rely solely on wire colors.
- The ribbon and servo leads have slack through the intended motion and are not trapped. The lid's circular slot deliberately clears the camera ribbon connector; it does not prove moving clearance.

The CRICKIT takes its own **5 V / 4 A DC barrel adapter**. Its HAT 5 V rail feeds Pi GPIO 5 V through Schottky diode D1 (MBA120). These supplies are **diode coupled, not isolated**: the barrel supply can energize the Pi with USB-C unplugged. There is no isolation jumper to remove. See the [HAT schematic](https://github.com/adafruit/Adafruit_Crickit_PCBs/blob/master/Adafruit%20Crickit%20HAT.sch) and [CRICKIT power guide](https://learn.adafruit.com/adafruit-crickit-hat-for-raspberry-pi-linux-computers/powering-crickit).

For first boot, keep the CRICKIT barrel unplugged and power the Pi from its USB-C wall supply. Your computer communicates with the Pi over Wi-Fi/SSH; the Pi's USB-C connection is for wall power in this setup.

## 3. Connect from your computer

Allow the first boot to finish. In Windows PowerShell or another computer's terminal, replace `YOUR_USERNAME` with the username chosen in Imager:

```text
ssh YOUR_USERNAME@deskbot.local
```

Accept the host key on this first connection and authenticate with your chosen password or key. If `.local` does not resolve, find the Pi's address in your router's device list and use `ssh YOUR_USERNAME@PI_IP_ADDRESS`. Use your actual hostname if you chose something other than `deskbot`.

Commands in the remaining sections are typed **inside that SSH session**, at the Pi's shell prompt.

## 4. Download the private repository

The GitHub account used here must have access to the private repository [OhR4tz/DeskBot](https://github.com/OhR4tz/DeskBot).

```bash
sudo apt update
sudo apt install -y git gh nano
gh auth login --web --git-protocol https
```

Select GitHub.com if asked and follow the device-code instructions. Open the shown URL on your computer, enter the displayed code, and sign in to the account with repository access. No graphical browser on the Pi is needed. If asked whether to authenticate Git, accept.

```bash
cd ~
gh repo clone OhR4tz/DeskBot
cd DeskBot
```

If cloning reports that the repository cannot be found, check that the source has been published and that the authenticated GitHub account has access. A private repository cannot be downloaded anonymously.

As an alternative, transfer only the project files from your computer into `~/DeskBot` using SCP/SFTP. Include `pyproject.toml`, `src`, `configs`, `scripts`, `deploy`, `tests`, and the documentation; `mechanical` is optional for running. Do not copy `.tools`, a Windows virtual environment, credentials, or development caches. Then `cd ~/DeskBot` on the Pi and continue below.

## 5. Install and check without moving motors

```bash
bash scripts/install-pi.sh
sudo reboot
```

The SSH session disconnects during reboot. Reconnect using the same SSH command and return to the project:

```bash
cd ~/DeskBot
bash scripts/preflight-pi.sh
```

The installer checks for a real 64-bit Raspberry Pi running Trixie, enables I2C, installs the Pi camera packages and dependencies, creates `.venv` with access to system packages, and installs DeskBot with its Pi and vision extras. On Linux/aarch64, the Pi extra includes `Adafruit-Blinka-Raspberry-Pi-PWM>=1.0.2`, the native PWM dependency needed by the current Blinka stack. It downloads the official hand model into `models/hand_landmarker.task` and the face model into `models/blaze_face_short_range.tflite`; these models are not bundled in Git. Internet access is needed for installation and downloads.

Preflight checks all three model paths, imports Picamera2, MediaPipe, `pwmio`, and `adafruit_motor.servo`, and checks that the CRICKIT driver package is installed. It checks the I2C device exists and requires an IMX500 to be enumerated by Picamera2, then lists cameras with `rpicam-hello --list-cameras`. It **does not open the CRICKIT board's I2C connection or initialize or move the servos**, so leave the barrel unplugged. The actual board connection is checked later during powered, unloaded servo centering. First camera inference startup can take time while the IMX500 model is loaded.

If setup stops, fix the reported error before proceeding. Useful checks are:

```bash
cat /etc/os-release
uname -m
rpicam-hello --list-cameras
ls -l /dev/i2c-1
```

The architecture should be `aarch64` and the OS codename `trixie`. Preflight stops with an explicit error if no IMX500 is enumerated. For a missing camera, shut down and disconnect both supplies before checking the ribbon, then boot again. For a missing I2C bus, rerun the installer and reboot. For missing model files, failed package downloads, or a missing native PWM dependency, rerun the installer after restoring connectivity.

## 6. Try simulation and the camera

Keep the CRICKIT barrel disconnected for these checks:

```bash
.venv/bin/deskbot simulate
```

This short simulation uses fake detections and fake servos; it needs no camera or CRICKIT.

```bash
.venv/bin/deskbot observe
```

`observe` runs the real camera, face detector, and hand detector and prints status about once a second, without opening servo hardware. Stand far enough back for a person box and hold a hand within your body's camera region. Test with one hand at a time initially. `person=yes` and `face=yes` mean fresh selected detections; `stale` means a recent target is being retained temporarily. `aim=face` centers the detected face; `face_error_px` gives its horizontal and vertical offset from frame center. If no face remains visible, `aim=person` uses an estimated head region, or `aim=hold` waits for a target. `reaction=rock_on` shows the happy nod/wiggle trigger. `reaction=middle_finger` looks to the calibrated downward tilt limit, holds, and returns: extend the middle finger while curling the index, ring, and little fingers; the thumb position is unrestricted. A steady pose triggers once; relax the hand before trying again and allow the cooldown.

Press **Ctrl+C** to stop. Then try the same pipeline with simulated motion:

```bash
.venv/bin/deskbot run
```

This is still a dry run: real servo hardware requires the explicit `--enable-servos` flag and completed calibration. On a Pi with a graphical desktop and a working local display, `observe --preview` or `run --preview` adds a camera window (`q` closes it). Omit `--preview` on Lite and ordinary SSH sessions.

## 7. Calibrate, then run interactively

Follow [the calibration guide](calibration.md) before adding the hardware flag. First electrically center each unknown servo separately with its linkage mechanically unloaded, then index the horns with both supplies off, and only then use assembled `calibrate` → `ATTACH`. Do not try an unknown assembled center simply by pointing the unpowered head forward. Once the full guide is complete and the head is supported near its checked neutral position:

```bash
.venv/bin/deskbot run --enable-servos
```

Watch the robot continuously for this first run and keep both power disconnects accessible. Check that it follows a person in the correct direction, respects the checked limits, and performs both reactions without cable tension. Stop with Ctrl+C. The software releases servo pulses rather than commanding a rest pose; support the head if gravity can move it.

## 8. Optional: start with systemd

Do this only after successful calibration and repeated interactive hardware runs. A service can energize the head without an interactive prompt, including after a reboot or failure restart. Keep its physical startup position and surroundings safe.

From your normal Pi user account in the project directory, print the actual values and make an editable copy:

```bash
whoami
pwd
cp deploy/deskbot.service.template /tmp/deskbot.service
nano /tmp/deskbot.service
```

Replace **every** `@USER@` with the username printed by `whoami` and **every** `@PROJECT_DIR@` with the absolute directory printed by `pwd` (for example `/home/alex/DeskBot`). Keep the `.venv/bin/deskbot`, config path, and `--enable-servos` portions. Do not put `~` in systemd paths. Save with Ctrl+O, Enter, then exit with Ctrl+X.

Install and start it manually first:

```bash
sudo install -m 0644 /tmp/deskbot.service /etc/systemd/system/deskbot.service
sudo systemctl daemon-reload
sudo systemctl start deskbot
sudo systemctl status deskbot --no-pager
journalctl -u deskbot -n 50 --no-pager
```

Only after this works, opt into startup at boot:

```bash
sudo systemctl enable deskbot
```

Stop the service before calibration, configuration changes, or another camera command. To stop it now and remove automatic startup:

```bash
sudo systemctl disable --now deskbot
```

To remove the installed service entirely after stopping it:

```bash
sudo rm /etc/systemd/system/deskbot.service
sudo systemctl daemon-reload
```

The service uses the same configuration and releases both servo channels on normal stop/SIGTERM. Release removes holding torque; it does not disconnect electrical power. A software stop cannot guarantee recovery from a power or hardware fault.

## 9. Check the 2 GB Pi under load

Defaults are 640 × 480, a requested camera-rate cap of 10 FPS, four camera buffers, one detected hand, and no preview. A short warmed sample on the 2 GB Pi reached 10 FPS; [the measured results and conditions](architecture.md#repository-map-and-development-checks) are recorded separately. Actual throughput and resource use can vary, so check your own run rather than treating that sample as a long-run guarantee.

While `observe` or a validated run is active, use a second SSH session:

```bash
free -h
top
vcgencmd measure_temp
vcgencmd get_throttled
```

Watch available RAM, DeskBot CPU use, temperature, and throttling. If load is excessive, stop DeskBot, keep `max_hands = 1`, and lower `fps` in `configs/deskbot.toml` (for example to `5`), then restart and assess tracking responsiveness. Avoid enabling a desktop preview just for normal use. `max_hands = 2` is available after measuring the cost.

For shutdown, stop DeskBot, run `sudo poweroff`, wait for shutdown to complete, then disconnect **both** USB-C and CRICKIT barrel power before wiring or mechanical work.
