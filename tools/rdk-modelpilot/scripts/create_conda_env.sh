#!/usr/bin/env bash
set -euo pipefail
if [ ! -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  echo "WSL 内未发现 conda。当前 yolo 环境可能只存在于 Windows Anaconda。"
  echo "修复方案：安装 WSL Miniconda，或在 SettingsPage 继续使用 Windows Anaconda 导出 ONNX。"
  exit 2
fi
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda create -n yolo python=3.10 -y || true
conda activate yolo
python -m pip install --upgrade pip
python -m pip install ultralytics torch torchvision onnx onnxruntime numpy opencv-python scipy pyyaml
