#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
echo "RAM: $(awk '/MemTotal:/ {printf "%.0f MiB", $2/1024}' /proc/meminfo)"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv; run scripts/install-pi.sh first." >&2
  exit 1
fi

.venv/bin/python - <<'PY'
from pathlib import Path
from deskbot.config import load

config = load('configs/deskbot.toml')
for label, path in [('IMX500 model', config.model), ('hand model', config.hand_model)]:
    if not Path(path).is_file():
        raise SystemExit(f'Missing {label}: {path}')
for label, module in [('Picamera2', 'picamera2'), ('MediaPipe', 'mediapipe'),
                      ('CRICKIT driver', 'adafruit_crickit')]:
    __import__(module)
    print(f'{label}: import OK')
print(f'Calibration armed: {config.calibrated}')
print(f'Pan world bounds: {config.pan.minimum}..{config.pan.maximum} deg')
print(f'Tilt world bounds: {config.tilt.minimum}..{config.tilt.maximum} deg')
PY

if [[ -e /dev/i2c-1 ]]; then
  echo 'I2C bus: present'
else
  echo 'I2C bus missing; reboot after enabling I2C.' >&2
  exit 1
fi

echo 'Detected cameras:'
rpicam-hello --list-cameras
echo 'No motors were moved by this preflight.'
