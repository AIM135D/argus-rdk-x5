from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from path_utils import ensure_dir, windows_to_wsl_path, wsl_to_windows_path


BASE_DIR = Path.cwd() if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "project_dir": "D:\\RDK_ModelPilot",
    "output_dir": "D:\\RDK_ModelPilot_Output",
    "rdk_model_zoo_windows": "D:\\rdk_model_zoo-main",
    "rdk_model_zoo_wsl": "/mnt/d/rdk_model_zoo-main",
    "export_script_windows": "D:\\rdk_model_zoo-main\\samples\\vision\\ultralytics_yolo\\x86\\export_monkey_patch.py",
    "export_script_wsl": "/mnt/d/rdk_model_zoo-main/samples/vision/ultralytics_yolo/x86/export_monkey_patch.py",
    "mapper_windows": "D:\\rdk_model_zoo-main\\samples\\vision\\ultralytics_yolo\\x86\\mapper.py",
    "mapper_wsl": "/mnt/d/rdk_model_zoo-main/samples/vision/ultralytics_yolo/x86/mapper.py",
    "conda_env": "yolo",
    "wsl_distro": "Ubuntu-22.04",
    "docker_image": "openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8",
    "install_mode": "AUTO",
    "default_imgsz": 640,
    "target": "RDK X5 bayes-e",
    "runtime_input": "NV12",
}


def init_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    ensure_dir(BASE_DIR / "logs")
    return load_config()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = CONFIG_PATH.with_suffix(".invalid.json")
        CONFIG_PATH.replace(backup)
        data = {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    install_mode = str(merged.get("install_mode", "AUTO")).upper()
    if install_mode not in {"AUTO", "SAFE", "NO"}:
        install_mode = "AUTO"
    merged["install_mode"] = install_mode
    CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def validate_paths(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    checks: dict[str, Any] = {}
    for key in [
        "project_dir",
        "output_dir",
        "rdk_model_zoo_windows",
        "export_script_windows",
        "mapper_windows",
    ]:
        value = cfg.get(key, "")
        checks[key] = {
            "path": value,
            "exists": Path(value).exists() if value else False,
        }
    checks["derived"] = {
        "rdk_model_zoo_wsl_from_windows": windows_to_wsl_path(cfg.get("rdk_model_zoo_windows", "")),
        "output_dir_wsl": windows_to_wsl_path(cfg.get("output_dir", "")),
        "output_dir_windows_from_wsl": wsl_to_windows_path(windows_to_wsl_path(cfg.get("output_dir", ""))),
    }
    return checks


def update_related_paths(config: dict[str, Any]) -> dict[str, Any]:
    """Keep WSL paths in sync when the user edits only the Windows paths."""
    cfg = dict(config)
    if cfg.get("rdk_model_zoo_windows") and not cfg.get("rdk_model_zoo_wsl"):
        cfg["rdk_model_zoo_wsl"] = windows_to_wsl_path(cfg["rdk_model_zoo_windows"])
    if cfg.get("export_script_windows") and not cfg.get("export_script_wsl"):
        cfg["export_script_wsl"] = windows_to_wsl_path(cfg["export_script_windows"])
    if cfg.get("mapper_windows") and not cfg.get("mapper_wsl"):
        cfg["mapper_wsl"] = windows_to_wsl_path(cfg["mapper_windows"])
    return cfg
