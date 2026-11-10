# Calibrate the assembled head

Calibrate the complete assembly with its camera, ribbon, lid, and servo leads in place. The supplied 3MF is a static assembly and does not establish a safe moving range. Start with the shipped bounds, pan ±10° and tilt ±5°. Pan is intended to reach ±55° (adjustable around ±50–60° if physically safe). The user-requested configurable tilt ceiling is now ±60°; approach any larger tilt range progressively.

Software enforces configurable ceilings of ±70° for pan and ±60° for tilt, while retaining the servo angle check of 0–180°. Those are maximum accepted settings, **not evidence that the mechanism clears them**. Leave smaller limits wherever the real assembly needs them. The narrow shipped defaults, 2° maximum jog, 5° maximum range-end edit, and slew limit are unchanged.

## Before the first attachment

**Establish electrical center before attaching an unknown servo to the head.** Pointing an unpowered head forward does not set servo zero. The controller has no position feedback, and assembled startup directly commands each configured center. Narrow bounds and the slew limiter cannot prevent a large initial jump. Never blindly retry an assembled center command after unexpected movement or binding.

For each axis with unknown neutral, complete this unloaded centering and horn-indexing process **one axis at a time**, before `calibrate` → `ATTACH`:

1. Stop DeskBot. If a service is installed, disable it for this work with `sudo systemctl disable --now deskbot` so it cannot restart during the following boots. Keep `calibrated = false` and the initial narrow bounds.
2. Shut down the Pi and disconnect **both** USB-C and CRICKIT barrel supplies. Support the head, then detach the selected horn/linkage from the head load. Secure the unloaded servo with room for its horn to move. Pan is port 1; tilt is port 2. Never force the shaft or gears. The HAT can keep the Pi powered from its barrel supply when USB-C is unplugged.
3. Restore Pi USB-C power, reconnect over SSH, and connect the CRICKIT's 5 V / 4 A barrel supply. Keep cables, fingers, and the unloaded horn clear, with the power disconnect accessible.
4. Run the selected command below and type **`DETACHED`** only after confirming that axis is mechanically unloaded. Observe it settle. Press **Enter** to release the servo pulses.
5. Shut down and disconnect **both** supplies again. Without turning the centered shaft, fit the horn onto its splines with the head pointing forward for pan, or level for tilt. Choose the closest suitable spline position; use only small software trim afterward. Refit with power off, never while the servo holds torque.
6. If fitting the horn turns the shaft or loses its known position, detach it and repeat electrical centering. Do not push the shaft back by hand or guess a large software correction from an observed swing.
7. Repeat the process separately for the other axis. Both unknown-neutral axes must be centered and mechanically aligned before assembled attachment.

For the unloaded pan servo, at the Linux shell in the project directory:

```bash
.venv/bin/deskbot center-servo pan
```

For the separately unloaded tilt servo, use:

```bash
.venv/bin/deskbot center-servo tilt
```

`center-servo` initializes and commands only the selected servo, at its configured center: by default 90° and nominally 1500 microseconds with the shipped pulse range. The other channel is untouched. The exact `DETACHED` confirmation is required before hardware access. This command does not sweep, change configuration, or arm calibration. It releases the selected channel when Enter is pressed or the command exits, including handled termination or SSH hangup. Power remains connected until you unplug it.

After both horns are aligned, restore power with the head supported and ribbon/leads free. Only then proceed to assembled calibration. The static 3MF and the lid's camera-cable clearance slot do not establish electrical neutral or safe motion.

The mapping assumes approximately 1:1 servo-to-head angles. If the mechanism uses a different ratio, measured head travel must guide your limits; the configured degrees are not a physical angle measurement.

## Start the interactive tool

From the Pi's project directory:

```bash
.venv/bin/deskbot calibrate
```

Read the prompt, confirm both axes have been electrically centered and mechanically aligned, and type **`ATTACH`** only when prepared for both servos to receive their center commands. A different response exits without attaching. After attachment, `show` displays the current logical pose and settings.

If anything binds, strains, buzzes persistently, heats, or pulls the ribbon, disconnect CRICKIT barrel power promptly. Do not use `neutral` to force a binding head back through an obstruction. Shut down and disconnect both supplies before inspecting. Resolve unknown neutral with the detached process above before retrying; narrower limits alone do not fix startup misalignment.

## Establish center and direction

Commands are typed at `calibrate>`, not at the Linux shell:

| Command | Effect |
| --- | --- |
| `show` | Print pose, axis settings, and calibration state. |
| `pan +1` / `pan -1` | Jog pan by 1° within the current bounds. |
| `tilt +1` / `tilt -1` | Jog tilt by 1° within the current bounds. |
| `neutral` | Move both axes back to logical zero within the checked path. |
| `center pan 91` | At neutral, set the pan center to 91°; changes are limited to 2° at a time. |
| `direction pan -1` | At neutral, reverse the mapping for pan. `1` is the other valid direction. |
| `range pan -15 15` | Change pan bounds; each end may change by at most 5° per edit. |
| `save` | Save current settings; this does not complete calibration. |
| `arm` | Check endpoint visits and request explicit calibration confirmation. |
| `quit` | Release servo pulses and leave the tool. |

Use `tilt` instead of `pan` for its corresponding center, direction, or range command. Jogs must be greater than zero and at most 2° in magnitude. The tool rejects jogs outside the current bounds.

After horn indexing, use tiny jogs to check direction. Positive pan should turn toward a target to the right in the camera image; positive tilt should look upward. Return to neutral before changing `direction`. At neutral, use `center` only for small final trim, at most 2° per edit. Center changes themselves command motion, so inspect each small change. A large offset requires detached electrical centering and power-off horn alignment, not repeated trim commands.

Changing center or direction disarms calibration and clears that axis's endpoint visits. Set them before exploring the larger range. Use `save` to keep the checked settings.

Pulse widths (`pulse_min` and `pulse_max`, initially 750 and 2250 microseconds) are not adjustable live. A changed pulse mapping can change the physical center and travel. If your particular servo needs another mapping, stop DeskBot and unplug the CRICKIT barrel supply. Keep Pi USB-C power on for SSH, then use `nano configs/deskbot.toml` to edit the pulse values, set `calibrated = false`, and restore narrow bounds. With the barrel unplugged, the HAT diode prevents Pi USB-C from feeding the servo power rail. Repeat detached centering and horn alignment for the affected axis before assembled calibration. Disconnect **both** supplies before handling wiring, electrical connectors, or the mechanical assembly.

## Expand only after checking clearance

Begin by approaching both ends of the initial pan range with repeated small jogs while tilt is neutral. Inspect the entire path, not only the endpoint. Return to neutral and do the same for tilt. Use the camera/ribbon's actual installed position when checking.

To grow pan toward ±55°, the practical range stages are **±10 → ±15 → ±20 → ±25 → ±30 → ±35 → ±40 → ±45 → ±50 → ±55**. Tilt starts **±5 → ±10 → ±15** and may continue in checked increments of at most 5° per range end, up to the ±60° ceiling. Requested 15° test milestones must still be approached through these range edits and 1–2° jogs; the interactive tool does not accept a 15° jog. At each stage:

1. Check that the next small expansion appears clear with the head supported and cables free.
2. At the prompt, change only that stage's bounds, for example `range pan -15 15` after checking the current ±10° path.
3. Approach each newly allowed end in 1–2° jogs, stopping immediately if clearance becomes uncertain. For an odd endpoint such as 15°, the last jog may be 1°.
4. Return through the checked path to neutral before the next expansion. Do not paste a sequence that automatically traverses multiple stages.

Check combined poses too: clearance at a pan endpoint with tilt at zero does not establish clearance at that pan position with tilt at either chosen endpoint. Slowly approach all four corners of your chosen final range with the same small jogs, checking ribbon slack, the lid opening, servo leads, and body/head contact along each path. Choose smaller or asymmetric limits if needed. When contracting a range, first return the current pose inside the proposed bounds; each range edit is still limited to 5° per end.

## Save and explicitly arm

Before arming, visit both configured endpoints of **each axis in this session**, check the combined corners, and return to neutral. Then type:

```text
save
arm
```

The tool requires endpoint visits within 1° of each configured end. This checks your command history, not mechanical clearance. After your physical checks, type **`CALIBRATED`** at the confirmation prompt. This writes `calibrated = true` to the configuration. `quit` releases both channels; support the head because releasing pulses removes holding torque.

Do not set `calibrated = true` by hand to bypass this process. Recalibrate after changing the camera/cable routing, horn alignment, center, direction, pulse mapping, or allowed range. Configuration files can be edited outside the tool, so the saved flag cannot verify that the physical assembly remains unchanged.

Now return to [the interactive hardware run in setup](setup.md#7-calibrate-then-run-interactively). Keep automatic startup disabled until the real tracking and both gesture reactions have been checked at your chosen limits.
