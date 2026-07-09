# RDK ModelPilot Windows Conda environment setup
$ErrorActionPreference = "Stop"
conda create -n yolo python=3.10 -y
conda run -n yolo python -m pip install --upgrade pip
conda run -n yolo python -m pip install ultralytics torch torchvision onnx onnxruntime numpy opencv-python scipy pyyaml
