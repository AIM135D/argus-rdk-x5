# config.py
# -*- coding: utf-8 -*-
"""ARGUS runtime configuration.

Values are read from ``ARGUS_CONFIG`` (default: ``configs/runtime.yaml``) and
can be overridden with ``ARGUS_<UPPERCASE_KEY>`` environment variables.
Hardware-facing features are deliberately disabled by default.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml
except Exception:  # PyYAML is optional until a YAML config file is used.
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_CONFIG = PROJECT_ROOT / "configs" / "runtime.yaml"


def _load_runtime_config() -> dict:
    config_path = Path(
        os.getenv("ARGUS_CONFIG", str(DEFAULT_RUNTIME_CONFIG))
    ).expanduser()
    if not config_path.exists():
        return {}
    if yaml is None:
        raise RuntimeError(
            f"ARGUS config exists at {config_path}, but PyYAML is not installed. "
            "Run: python3 -m pip install -r requirements.txt"
        )
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as exc:
        raise RuntimeError(f"Unable to read ARGUS config {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"ARGUS config must be a YAML object: {config_path}")
    return data


_RUNTIME = _load_runtime_config()


def _value(key: str, default):
    env_value = os.getenv(f"ARGUS_{key.upper()}")
    return env_value if env_value is not None else _RUNTIME.get(key, default)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _project_path(key: str, default: str) -> str:
    path = Path(str(_value(key, default))).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


# 默认危险区域（多区域版本）
DEFAULT_DANGER_ZONES = [
    {
        "id": 1,
        "name": "默认危险区",
        "zone": [100, 100, 500, 400],
        "risk_level": "high",
        "enabled": True,
        "require_helmet": True,
        "require_vest": True,
    }
]
DEFAULT_DANGER_ZONE = DEFAULT_DANGER_ZONES[0]["zone"][:]

# 模型接口必须与训练/转换产物一致。
TARGET_NAMES = ["person"]
CLASS_NAMES = ["person", "helmet", "reflective_vest"]
MODEL_PATH = _project_path(
    "model_path", "models/argus_ppe_dfl_640_rdkx5.bin"
)
CLASSES_NUM = 3
REG_MAX = 16
STRIDES = [8, 16, 32]

# 摄像头和视频流。
CAMERA_INDEX = int(_value("camera_index", 0))
STREAM_WIDTH = int(_value("stream_width", 640))
STREAM_HEIGHT = int(_value("stream_height", 360))
JPEG_QUALITY = int(_value("jpeg_quality", 50))

# 检测阈值。
SCORE_THRESHOLD = float(_value("score_threshold", 0.40))
NMS_THRESHOLD = float(_value("nms_threshold", 0.70))
NMS_TOP_K = int(_value("nms_top_k", 50))

# 服务与硬件安全开关。
HOST = str(_value("host", "127.0.0.1"))
PORT = int(_value("port", 8000))
HARDWARE_ENABLED = _as_bool(_value("hardware_enabled", False))
SERVO_ENABLED = _as_bool(_value("servo_enabled", False))
BUZZER_ENABLED = _as_bool(_value("buzzer_enabled", False))
LIGHT_ENABLED = _as_bool(_value("light_enabled", False))
LLM_BRIDGE_ENABLED = _as_bool(_value("llm_bridge_enabled", False))

# ESP32 串口和协议。
ESP32_PORT = str(_value("esp32_port", "/dev/ttyUSB0"))
ESP32_BAUDRATE = int(_value("esp32_baudrate", 115200))
ESP32_PROTOCOL = str(_value("esp32_protocol", "A")).upper()
ESP32_SEND_HZ = float(_value("esp32_send_hz", 12.0))

# 抓拍和运行时配置文件。
LONG_DANGER_CAPTURE_SECONDS = float(
    _value("long_danger_capture_seconds", 3.0)
)
CAPTURE_COOLDOWN_SECONDS = float(_value("capture_cooldown_seconds", 8.0))
MAX_EVENT_LOGS = int(_value("max_event_logs", 30))
DANGER_ZONE_FILE = _project_path(
    "danger_zone_file", "configs/danger_zones.runtime.json"
)
SERVO_CALIBRATION_FILE = _project_path(
    "servo_calibration_file", "configs/servo_calibration.runtime.json"
)
