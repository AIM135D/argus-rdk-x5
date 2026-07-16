#!/usr/bin/env bash
set -euo pipefail
echo "[RDK ModelPilot] Preparing WSL environment for Ubuntu-22.04"
sudo apt-get update
sudo apt-get install -y git curl python3 python3-pip
if [ ! -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  echo "[RDK ModelPilot] Miniconda was not found in WSL."
  echo "[RDK ModelPilot] Install it if you want to use WSL-side conda:"
  echo "curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh"
  echo "bash /tmp/miniconda.sh -b -p $HOME/miniconda3"
fi
if [ ! -d "/mnt/d/rdk_model_zoo-main" ]; then
  git clone https://github.com/D-Robotics/rdk_model_zoo.git "/mnt/d/rdk_model_zoo-main"
fi
