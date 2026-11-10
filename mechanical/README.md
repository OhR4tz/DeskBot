# Supplied RoboBuddy assembly

[`RoboBuddy.3mf`](RoboBuddy.3mf) is the user's supplied model of the already assembled robot, copied here as the mechanical reference. It contains a static OpenCASCADE assembly in millimeters, with 13 named parts and an overall bounding size of approximately **86 × 84 × 181.9 mm**.

The slot in the lid deliberately provides room for the Raspberry Pi AI Camera ribbon connector. The robot uses one camera in its head. The file does not model the camera hardware or cables, encode electrical servo neutral, or include a motion or swept-clearance validation. Electrical centering and power-off horn indexing must be established on the actual servos.

Do not infer that the head can safely reach pan ±55° or tilt ±15° from this static model. Clearance, horn alignment, cable slack, and all combined pan/tilt corner poses must be checked on the actual assembly using [the calibration guide](../docs/calibration.md). Start with the software's narrow uncalibrated bounds and stop wherever physical clearance requires smaller limits.

No geometry changes or new mechanical fit claims are included in this software project.
