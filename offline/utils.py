# utils.py
# -*- coding: utf-8 -*-

import json
import os

import cv2
import numpy as np

from config import (
    DEFAULT_DANGER_ZONE,
    DEFAULT_DANGER_ZONES,
    DANGER_ZONE_FILE,
    STREAM_WIDTH,
    STREAM_HEIGHT,
)


def normalize_zone(zone):
    try:
        x1, y1, x2, y2 = [int(v) for v in zone]
    except Exception:
        return DEFAULT_DANGER_ZONE[:]

    x1 = max(0, min(STREAM_WIDTH - 1, x1))
    x2 = max(0, min(STREAM_WIDTH - 1, x2))
    y1 = max(0, min(STREAM_HEIGHT - 1, y1))
    y2 = max(0, min(STREAM_HEIGHT - 1, y2))

    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1

    if x2 - x1 < 5 or y2 - y1 < 5:
        return DEFAULT_DANGER_ZONE[:]

    return [x1, y1, x2, y2]


def _make_default_zone_item(zone_id=1):
    return {
        "id": int(zone_id),
        "name": f"危险区{zone_id}",
        "zone": DEFAULT_DANGER_ZONE[:],
        "risk_level": "high",
        "enabled": True,
        "require_helmet": False,
        "require_vest": False,
    }


def normalize_zone_item(item, fallback_id=1):
    if isinstance(item, dict):
        raw_zone = item.get("zone", DEFAULT_DANGER_ZONE[:])

        try:
            zone_id = int(item.get("id", fallback_id))
        except Exception:
            zone_id = int(fallback_id)

        name = str(item.get("name", f"危险区{zone_id}")).strip()
        if not name:
            name = f"危险区{zone_id}"

        risk_level = str(item.get("risk_level", "high")).strip().lower()
        if risk_level not in ("high", "medium", "low"):
            risk_level = "high"

        enabled = bool(item.get("enabled", True))
        require_helmet = bool(item.get("require_helmet", False))
        require_vest = bool(item.get("require_vest", False))

        return {
            "id": zone_id,
            "name": name,
            "zone": normalize_zone(raw_zone),
            "risk_level": risk_level,
            "enabled": enabled,
            "require_helmet": require_helmet,
            "require_vest": require_vest,
        }

    if isinstance(item, list) and len(item) == 4:
        zone_id = int(fallback_id)
        return {
            "id": zone_id,
            "name": f"危险区{zone_id}",
            "zone": normalize_zone(item),
            "risk_level": "high",
            "enabled": True,
            "require_helmet": False,
            "require_vest": False,
        }

    return _make_default_zone_item(fallback_id)


def normalize_danger_zones(zones):
    if not isinstance(zones, list) or not zones:
        return [normalize_zone_item(DEFAULT_DANGER_ZONES[0], 1)]

    normalized = []
    used_ids = set()

    for idx, item in enumerate(zones, start=1):
        zone_item = normalize_zone_item(item, idx)

        zone_id = zone_item["id"]
        while zone_id in used_ids:
            zone_id += 1
        zone_item["id"] = zone_id

        if not zone_item["name"]:
            zone_item["name"] = f"危险区{zone_id}"

        used_ids.add(zone_id)
        normalized.append(zone_item)

    if not normalized:
        return [normalize_zone_item(DEFAULT_DANGER_ZONES[0], 1)]

    return normalized


def load_danger_zones():
    if not os.path.exists(DANGER_ZONE_FILE):
        return normalize_danger_zones(DEFAULT_DANGER_ZONES)

    try:
        with open(DANGER_ZONE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()

            if not content:
                return normalize_danger_zones(DEFAULT_DANGER_ZONES)

            data = json.loads(content)

        if isinstance(data, dict) and "danger_zones" in data:
            return normalize_danger_zones(data["danger_zones"])

        if isinstance(data, dict) and "danger_zone" in data:
            return normalize_danger_zones([
                {
                    "id": 1,
                    "name": "默认危险区",
                    "zone": data["danger_zone"],
                    "risk_level": "high",
                    "enabled": True,
                    "require_helmet": False,
                    "require_vest": False,
                }
            ])

        if isinstance(data, list):
            if len(data) == 4 and all(isinstance(v, (int, float)) for v in data):
                return normalize_danger_zones([
                    {
                        "id": 1,
                        "name": "默认危险区",
                        "zone": data,
                        "risk_level": "high",
                        "enabled": True,
                        "require_helmet": False,
                        "require_vest": False,
                    }
                ])
            return normalize_danger_zones(data)

    except Exception as e:
        print("⚠️ danger_zone.json 解析失败，使用默认值:", e)

    return normalize_danger_zones(DEFAULT_DANGER_ZONES)


def save_danger_zones(zones):
    normalized = normalize_danger_zones(zones)
    try:
        with open(DANGER_ZONE_FILE, "w", encoding="utf-8") as f:
            json.dump({"danger_zones": normalized}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("保存危险区域配置失败:", e)
        return False


def load_danger_zone():
    zones = load_danger_zones()
    if zones:
        return zones[0]["zone"][:]
    return DEFAULT_DANGER_ZONE[:]


def save_danger_zone(zone):
    zone = normalize_zone(zone)
    zones = load_danger_zones()

    if not zones:
        zones = normalize_danger_zones(DEFAULT_DANGER_ZONES)

    zones[0]["zone"] = zone[:]
    return save_danger_zones(zones)


def bgr_to_nv12(frame_bgr: np.ndarray, dst_w: int, dst_h: int) -> np.ndarray:
    resized = cv2.resize(frame_bgr, (dst_w, dst_h))
    area = dst_w * dst_h

    yuv420p = cv2.cvtColor(resized, cv2.COLOR_BGR2YUV_I420).reshape(area * 3 // 2)
    y = yuv420p[:area]

    uv_planar = yuv420p[area:].reshape((2, area // 4))
    uv_packed = uv_planar.transpose((1, 0)).reshape(area // 2)

    nv12_data = np.empty_like(yuv420p)
    nv12_data[:area] = y
    nv12_data[area:] = uv_packed

    return nv12_data