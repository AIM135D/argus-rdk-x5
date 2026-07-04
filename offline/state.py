# state.py
# -*- coding: utf-8 -*-

import base64
import copy
import threading
import time

import cv2
import numpy as np

from config import DEFAULT_DANGER_ZONE, MAX_EVENT_LOGS
from utils import (
    load_danger_zones,
    normalize_danger_zones,
    normalize_zone,
    save_danger_zones,
)


def _default_zone_runtime(zone_item):
    return {
        "id": zone_item["id"],
        "name": zone_item["name"],
        "risk_level": zone_item.get("risk_level", "high"),
        "enabled": bool(zone_item.get("enabled", True)),
        "require_helmet": bool(zone_item.get("require_helmet", False)),
        "require_vest": bool(zone_item.get("require_vest", False)),
        "active": False,
        "danger_start_time": None,
        "danger_duration": 0.0,
        "danger_count": 0,
        "last_capture_time": 0.0,
        "last_alert": "-",
    }


class GlobalState:
    def __init__(self):
        self.latest_jpeg = None

        self.latest_info = {
            "fps": 0.0,
            "infer_ms": 0.0,
            "online": 0,
            "danger": False,
            "danger_count": 0,
            "last_alert": "-",
            "frame_id": 0,
            "current_person_count": 0,
            "danger_person_count": 0,
            "danger_duration": 0.0,

            "ppe_violation_count": 0,
            "missing_helmet_count": 0,
            "missing_vest_count": 0,

            "cpu_usage": None,
            "mem_usage": None,
            "cpu_temp": None,
            "bpu_temp": None,
            "bpu_usage": None,
            "power_w": None,

            "zone_stats": [],
            "active_zone_names": [],
            "top_risk_zone_name": "-",

            # ESP32 声光/指向模块目标字段
            "target_valid": False,
            "target_x": -1,
            "target_y": -1,
            "target_conf": 0.0,
            "target_zone_id": None,
            "target_zone_name": "-",
            "target_reason": "lost",
            "target_point_type": "none",
            "target_priority": 0,
            "target_stable": False,
            "target_hold": False,
            "target_track_id": None,
            "risk_score": 0.0,
            "risk_candidate_count": 0,
            "risk_candidates": [],
            "track_count": 0,
            "target_switch_count": 0,
            "target_switch_reason": "init",
            "target_utility": 0.0,
            "alarm_level": "none",

            # 舵机标定映射与串口状态
            "servo_aim_valid": False,
            "servo_pan": None,
            "servo_tilt": None,
            "servo_map_mode": "none",
            "servo_map_name": "-",
            "servo_hold_mode": False,
            "control_state": "IDLE",
            "control_state_age": 0.0,
            "control_allow_alarm": False,
            "manual_aim_active": False,
            "manual_aim_pan": 90,
            "manual_aim_tilt": 90,
            "manual_aim_beep": 0,
            "manual_aim_until": 0.0,
            "buzzer_level": 0,
            "buzzer_active": False,
            "esp32_connected": False,
            "esp32_port": "-",
            "esp32_protocol": "-",
            "esp32_last_cmd": "",
            "esp32_last_ack": "",
            "esp32_last_error": "",
            "esp32_seq": 0,
        }

        self.clients = []
        self.lock = threading.Lock()
        self.running = True
        self.prev_danger = False

        self.latest_frame = None
        self.latest_frame_seq = 0
        self.frame_lock = threading.Lock()

        self.danger_start_time = None

        self.event_logs = []
        self.next_event_log_id = 1
        self.last_capture_time = 0.0

        self.danger_zones = load_danger_zones()

        self.zone_runtime = {}
        self._sync_zone_runtime_locked()

    def _sync_zone_runtime_locked(self):
        new_runtime = {}
        for zone in self.danger_zones:
            zone_id = int(zone["id"])
            if zone_id in self.zone_runtime:
                old = self.zone_runtime[zone_id]
                old["name"] = zone["name"]
                old["risk_level"] = zone.get("risk_level", "high")
                old["enabled"] = bool(zone.get("enabled", True))
                old["require_helmet"] = bool(zone.get("require_helmet", False))
                old["require_vest"] = bool(zone.get("require_vest", False))
                new_runtime[zone_id] = old
            else:
                new_runtime[zone_id] = _default_zone_runtime(zone)
        self.zone_runtime = new_runtime


state = GlobalState()


def get_current_danger_zones():
    with state.lock:
        return copy.deepcopy(state.danger_zones)


def get_current_zone_runtime():
    with state.lock:
        return copy.deepcopy(state.zone_runtime)


def set_current_danger_zones(zones):
    normalized_zones = normalize_danger_zones(zones)
    ok = save_danger_zones(normalized_zones)

    if ok:
        with state.lock:
            state.danger_zones = copy.deepcopy(normalized_zones)
            state._sync_zone_runtime_locked()

    return ok, normalized_zones


def get_current_danger_zone():
    with state.lock:
        if state.danger_zones:
            return state.danger_zones[0]["zone"][:]
    return DEFAULT_DANGER_ZONE[:]


def set_current_danger_zone(zone):
    zone = normalize_zone(zone)

    with state.lock:
        current_zones = copy.deepcopy(state.danger_zones)

    if not current_zones:
        current_zones = normalize_danger_zones([])

    current_zones[0]["zone"] = zone[:]
    ok = save_danger_zones(current_zones)

    if ok:
        with state.lock:
            state.danger_zones = copy.deepcopy(current_zones)
            state._sync_zone_runtime_locked()

    return ok, zone


def add_event_log(event_type: str, message: str, image_bgr: np.ndarray = None, extra=None):
    log_item = {
        "id": None,
        "type": event_type,
        "time": time.strftime("%H:%M:%S"),
        "message": message,
        "image": None,
    }

    if extra and isinstance(extra, dict):
        log_item.update(extra)

    if image_bgr is not None:
        try:
            ok, img_buffer = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                log_item["image"] = base64.b64encode(img_buffer.tobytes()).decode("utf-8")
        except Exception as e:
            print("日志图片编码失败:", e)

    with state.lock:
        log_item["id"] = state.next_event_log_id
        state.next_event_log_id += 1

        state.event_logs.insert(0, log_item)

        if len(state.event_logs) > MAX_EVENT_LOGS:
            state.event_logs = state.event_logs[:MAX_EVENT_LOGS]

        return log_item["id"]


def update_event_log(log_id: int, patch: dict):
    if not isinstance(patch, dict):
        return False

    try:
        target_id = int(log_id)
    except Exception:
        return False

    with state.lock:
        for item in state.event_logs:
            try:
                if int(item.get("id", -1)) == target_id:
                    item.update(copy.deepcopy(patch))
                    return True
            except Exception:
                continue

    return False