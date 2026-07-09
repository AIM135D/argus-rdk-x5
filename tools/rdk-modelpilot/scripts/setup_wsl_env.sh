#!/usr/bin/env bash
set -euo pipefail
echo "[RDK ModelPilot] Preparing WSL environment"
sudo apt-get update
sudo apt-get install -y git curl python3 python3-pip
if [ ! -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  echo "[RDK ModelPilot] WSL 内未发现 conda。当前 yolo 环境可能只存在于 Windows Anaconda。"
  echo "[RDK ModelPilot] 可安装 WSL Miniconda，或继续使用 Windows Anaconda 完成 ONNX 导出。"
fi
if [ ! -d "/mnt/d/rdk_model_zoo-main" ]; then
  git clone https://github.com/D-Robotics/rdk_model_zoo.git /mnt/d/rdk_model_zoo-main
fi
