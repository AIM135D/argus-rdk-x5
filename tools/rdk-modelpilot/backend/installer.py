from __future__ import annotations

from pathlib import Path
from typing import Any

from config_manager import BASE_DIR, load_config
from env_checker import PYTHON_PACKAGES, check_environment
from path_utils import ensure_dir
from utils import LOG_DIR, append_log, find_conda_executable, run_command


RDK_MODEL_ZOO_URL = "https://github.com/D-Robotics/rdk_model_zoo.git"


def generate_install_scripts(config: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = config or load_config()
    scripts_dir = ensure_dir(BASE_DIR / "scripts")
    conda_env = cfg["conda_env"]
    docker_image = cfg["docker_image"]
    distro = cfg["wsl_distro"]
    rdk_win = cfg["rdk_model_zoo_windows"]
    rdk_wsl = cfg["rdk_model_zoo_wsl"]
    packages = " ".join(PYTHON_PACKAGES.keys())

    scripts = {
        "install_windows_prereq.ps1": f"""# RDK ModelPilot Windows prerequisite helper
# Run as Administrator when prompted by the application.
$ErrorActionPreference = "Stop"
Write-Host "Enabling WSL and Virtual Machine Platform..."
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
wsl --set-default-version 2
Write-Host "If Ubuntu is missing, install it with:"
Write-Host "  wsl --install -d {distro}"
Write-Host "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ or via winget:"
Write-Host "  winget install Docker.DockerDesktop"
Write-Host "A Windows restart may be required."
""",
        "setup_wsl_env.sh": f"""#!/usr/bin/env bash
set -euo pipefail
echo "[RDK ModelPilot] Preparing WSL environment for {distro}"
sudo apt-get update
sudo apt-get install -y git curl python3 python3-pip
if [ ! -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  echo "[RDK ModelPilot] Miniconda was not found in WSL."
  echo "[RDK ModelPilot] Install it if you want to use WSL-side conda:"
  echo "curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh"
  echo "bash /tmp/miniconda.sh -b -p $HOME/miniconda3"
fi
if [ ! -d "{rdk_wsl}" ]; then
  git clone {RDK_MODEL_ZOO_URL} "{rdk_wsl}"
fi
""",
        "create_conda_env.ps1": f"""# RDK ModelPilot Windows Conda environment setup
$ErrorActionPreference = "Stop"
conda create -n {conda_env} python=3.10 -y
conda run -n {conda_env} python -m pip install --upgrade pip
conda run -n {conda_env} python -m pip install {packages}
""",
        "create_conda_env.sh": f"""#!/usr/bin/env bash
set -euo pipefail
if [ ! -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  echo "WSL 内未发现 conda。当前 yolo 环境可能只存在于 Windows Anaconda。"
  echo "修复方案：安装 WSL Miniconda，或在 SettingsPage 继续使用 Windows Anaconda 导出 ONNX。"
  exit 2
fi
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda create -n {conda_env} python=3.10 -y || true
conda activate {conda_env}
python -m pip install --upgrade pip
python -m pip install {packages}
""",
        "pull_openexplorer_image.ps1": f"""# RDK ModelPilot OpenExplorer image pull
$ErrorActionPreference = "Stop"
docker pull {docker_image}
docker run --rm {docker_image} hb_mapper --help
""",
        "run_mapper_in_docker.sh": f"""#!/usr/bin/env bash
set -euo pipefail
IMAGE="${{RDK_MODELPILOT_DOCKER_IMAGE:-{docker_image}}}"
TASK_DIR="${{1:-}}"
RDK_DIR="${{RDK_MODELPILOT_RDK_MODEL_ZOO:-{rdk_wsl}}}"
if [ -z "$TASK_DIR" ]; then
  echo "Usage: run_mapper_in_docker.sh /mnt/d/RDK_ModelPilot_Output/task_dir"
  exit 2
fi
docker run --rm \\
  -v "$TASK_DIR:/workspace/task" \\
  -v "$RDK_DIR:/workspace/rdk_model_zoo:ro" \\
  "$IMAGE" bash -lc "hb_mapper --help && python3 /workspace/rdk_model_zoo/samples/vision/ultralytics_yolo/x86/mapper.py --help || true"
""",
    }

    written: dict[str, str] = {}
    for name, content in scripts.items():
        path = scripts_dir / name
        path.write_text(content, encoding="utf-8", newline="\n")
        written[name] = str(path)
    return written


def install_environment() -> dict[str, Any]:
    cfg = load_config()
    install_log = LOG_DIR / "install.log"
    append_log(install_log, "RDK ModelPilot environment install/repair started")
    ensure_dir(cfg["output_dir"])
    ensure_dir(LOG_DIR)
    scripts = generate_install_scripts(cfg)
    before = check_environment(cfg)
    actions: list[dict[str, Any]] = []
    user_actions: list[dict[str, str]] = []

    mode = str(cfg.get("install_mode", "AUTO")).upper()
    if mode == "NO":
        append_log(install_log, "Install mode is NO. Scripts generated only.")
        return {
            "mode": mode,
            "scripts": scripts,
            "actions": actions,
            "user_actions": [{"title": "安装策略为 NO", "detail": "已生成脚本，但不会自动执行修复命令。"}],
            "before": before,
            "after": None,
            "log_path": str(install_log),
        }

    if not before["wsl"]["cli"]["ok"] or not before["wsl"]["distros"]["ok"]:
        user_actions.append(
            {
                "title": "需要启用或安装 WSL2",
                "detail": f"请以管理员权限运行 {scripts['install_windows_prereq.ps1']}，必要时重启，然后安装 {cfg['wsl_distro']}。",
            }
        )
    if not before["docker"]["cli"]["ok"] or not before["docker"]["running"]["ok"]:
        user_actions.append(
            {
                "title": "需要安装或启动 Docker Desktop",
                "detail": f"请安装并启动 Docker Desktop；可参考 {scripts['install_windows_prereq.ps1']}。",
            }
        )

    conda_executable = find_conda_executable(cfg)
    if before["conda"]["cli"]["ok"] and conda_executable:
        if not before["conda"]["env_exists"]["ok"]:
            result = run_command([conda_executable, "create", "-n", cfg["conda_env"], "python=3.10", "-y"], install_log, timeout=1800)
            actions.append({"name": f"创建 Conda 环境 {cfg['conda_env']}", "result": result.to_dict()})
        install_packages = [
            "ultralytics",
            "torch",
            "torchvision",
            "onnx",
            "onnxruntime",
            "numpy",
            "opencv-python",
            "scipy",
            "pyyaml",
        ]
        missing_packages = [
            name for name in install_packages
            if not before.get("python_packages", {}).get(name, {}).get("ok")
        ]
        if missing_packages:
            result = run_command(
                [conda_executable, "run", "-n", cfg["conda_env"], "python", "-m", "pip", "install", *missing_packages],
                install_log,
                timeout=3600,
            )
            actions.append({"name": "安装/修复缺失的 Python 依赖", "packages": missing_packages, "result": result.to_dict()})
    else:
        user_actions.append(
            {
                "title": "未检测到 Conda",
                "detail": "请安装 Anaconda/Miniconda，或把 conda 加入 PATH。若 WSL 内没有 conda，软件会继续优先使用 Windows Anaconda 导出 ONNX。",
            }
        )

    if before["docker"]["cli"]["ok"] and before["docker"]["running"]["ok"] and not before["docker"]["image"]["ok"]:
        result = run_command(["docker", "pull", cfg["docker_image"]], install_log, timeout=7200)
        actions.append({"name": "拉取 OpenExplorer Docker 镜像", "result": result.to_dict()})

    rdk_repo = Path(cfg["rdk_model_zoo_windows"])
    if not rdk_repo.exists():
        parent = rdk_repo.parent
        ensure_dir(parent)
        if before["windows"]["git"]["ok"]:
            result = run_command(["git", "clone", RDK_MODEL_ZOO_URL, str(rdk_repo)], install_log, timeout=3600)
            actions.append({"name": "克隆 rdk_model_zoo", "result": result.to_dict()})
        else:
            user_actions.append(
                {
                    "title": "无法克隆 rdk_model_zoo",
                    "detail": "Git 不可用。请先安装 Git，或手动下载 rdk_model_zoo 到 SettingsPage 中配置的路径。",
                }
            )

    after = check_environment(cfg)
    append_log(install_log, "RDK ModelPilot environment install/repair finished")
    return {
        "mode": mode,
        "scripts": scripts,
        "actions": actions,
        "user_actions": user_actions,
        "before": before,
        "after": after,
        "log_path": str(install_log),
    }
