#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
echo "RAM: $(awk '/MemTotal:/ {printf "%.0f MiB", $2/1024}' /proc/meminfo)"

if [[ "$(uname -m)" != "aarch64" ]] || ! grep -qi 'Raspberry Pi' /proc/device-tree/model; then
  echo "Run this on a 64-bit Raspberry Pi OS installation." >&2
  exit 1
fi
. /etc/os-release
if [[ "${VERSION_CODENAME:-}" != "trixie" ]]; then
  echo "Expected current Raspberry Pi OS (Trixie); found ${VERSION_CODENAME:-unknown}." >&2
  exit 1
fi

sudo apt update
sudo apt install -y imx500-all python3-picamera2 python3-opencv python3-numpy \
  python3-venv python3-dev build-essential i2c-tools libgpiod-dev \
  python3-libgpiod libportaudio2 curl
sudo raspi-config nonint do_i2c 0

if [[ ! -d .venv ]]; then
  python3 -m venv --system-site-packages .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[pi,vision]'

mkdir -p models
model_path="models/hand_landmarker.task"
model_url="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
if [[ ! -s "$model_path" ]]; then
  curl --fail --location --retry 3 "$model_url" --output "${model_path}.download"
  mv "${model_path}.download" "$model_path"
fi

echo "Installed. Reboot if firmware/I2C was just enabled, then run scripts/preflight-pi.sh."
