#!/usr/bin/env bash
set -euo pipefail
IMAGE="${RDK_MODELPILOT_DOCKER_IMAGE:-openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8}"
TASK_DIR="${1:-}"
RDK_DIR="${RDK_MODELPILOT_RDK_MODEL_ZOO:-/mnt/d/rdk_model_zoo-main}"
if [ -z "$TASK_DIR" ]; then
  echo "Usage: run_mapper_in_docker.sh /mnt/d/RDK_ModelPilot_Output/task_dir"
  exit 2
fi
docker run --rm \
  -v "$TASK_DIR:/workspace/task" \
  -v "$RDK_DIR:/workspace/rdk_model_zoo:ro" \
  "$IMAGE" bash -lc "hb_mapper --help && python3 /workspace/rdk_model_zoo/samples/vision/ultralytics_yolo/x86/mapper.py --help || true"
