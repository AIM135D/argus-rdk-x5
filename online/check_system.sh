#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$APP_DIR/.." && pwd)"
MODEL_PATH="${ARGUS_MODEL_PATH:-$PROJECT_ROOT/models/argus_ppe_dfl_640_rdkx5.bin}"
SERIAL_PORT="${ARGUS_ESP32_PORT:-/dev/ttyUSB0}"
cd "$APP_DIR"

echo "[1/5] Python"
python3 --version
echo "[2/5] RDK runtime"
python3 -c 'from hobot_dnn import pyeasy_dnn; print("OK hobot_dnn")' 2>/dev/null || echo "WARN hobot_dnn unavailable"
echo "[3/5] Model"
[[ -f "$MODEL_PATH" ]] && echo "OK $MODEL_PATH" || echo "WARN model missing: $MODEL_PATH"
echo "[4/5] Serial"
[[ -e "$SERIAL_PORT" ]] && ls -l "$SERIAL_PORT" || echo "INFO serial disabled or absent: $SERIAL_PORT"
echo "[5/5] Config"
python3 -c 'import json, pathlib, yaml; root=pathlib.Path.cwd().parent; json.load(open(root/"configs/danger_zones.example.json")); yaml.safe_load(open(root/"configs/runtime.example.yaml")); print("OK examples")'
