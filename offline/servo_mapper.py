# -*- coding: utf-8 -*-
"""固定广角图像坐标到舵机角度的轻量映射。

默认使用 3x3 稀疏标定网格 + 分片双线性插值；
可为某些危险区启用固定角度覆盖。配置文件为 servo_calibration.json。
"""

from __future__ import annotations

import copy
import json
import os
import threading

from config import SERVO_CALIBRATION_FILE, STREAM_HEIGHT, STREAM_WIDTH


CALIBRATION_FILE = SERVO_CALIBRATION_FILE
_DEFAULT = {
    "version": 1,
    "frame_width": STREAM_WIDTH,
    "frame_height": STREAM_HEIGHT,
    "mode": "grid",
    "grid": [
        [
            {"u": 0, "v": 0, "pan": 45, "tilt": 60},
            {"u": STREAM_WIDTH // 2, "v": 0, "pan": 90, "tilt": 60},
            {"u": STREAM_WIDTH - 1, "v": 0, "pan": 135, "tilt": 60},
        ],
        [
            {"u": 0, "v": STREAM_HEIGHT // 2, "pan": 45, "tilt": 82},
            {"u": STREAM_WIDTH // 2, "v": STREAM_HEIGHT // 2, "pan": 90, "tilt": 82},
            {"u": STREAM_WIDTH - 1, "v": STREAM_HEIGHT // 2, "pan": 135, "tilt": 82},
        ],
        [
            {"u": 0, "v": STREAM_HEIGHT - 1, "pan": 45, "tilt": 105},
            {"u": STREAM_WIDTH // 2, "v": STREAM_HEIGHT - 1, "pan": 90, "tilt": 105},
            {"u": STREAM_WIDTH - 1, "v": STREAM_HEIGHT - 1, "pan": 135, "tilt": 105},
        ],
    ],
    "zone_overrides": {},
    "limits": {"pan_min": 10, "pan_max": 170, "tilt_min": 35, "tilt_max": 135},
    "offset": {"pan": 0, "tilt": 0},
}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class ServoMapper:
    def __init__(self, path: str = CALIBRATION_FILE):
        self.path = path
        self._lock = threading.Lock()
        self._config = copy.deepcopy(_DEFAULT)
        self.reload()

    def reload(self):
        config = copy.deepcopy(_DEFAULT)
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    config.update(loaded)
        except Exception as e:
            print(f"⚠️ 舵机标定文件读取失败，使用默认映射: {e}")
        with self._lock:
            self._config = config
        return self.snapshot()

    def save(self, config: dict):
        if not isinstance(config, dict):
            raise ValueError("calibration config must be dict")
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        return self.reload()

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._config)

    @staticmethod
    def _find_interval(values, x):
        if len(values) < 2:
            return 0, 0, 0.0
        if x <= values[0]:
            return 0, 1, 0.0
        if x >= values[-1]:
            return len(values) - 2, len(values) - 1, 1.0
        for i in range(len(values) - 1):
            if values[i] <= x <= values[i + 1]:
                denom = max(1e-6, values[i + 1] - values[i])
                return i, i + 1, (x - values[i]) / denom
        return 0, 1, 0.0

    def map(self, cx, cy, zone_id=None):
        cfg = self.snapshot()
        limits = cfg.get("limits", {})
        offset = cfg.get("offset", {})
        pan_min = float(limits.get("pan_min", 10))
        pan_max = float(limits.get("pan_max", 170))
        tilt_min = float(limits.get("tilt_min", 35))
        tilt_max = float(limits.get("tilt_max", 135))
        pan_offset = float(offset.get("pan", 0))
        tilt_offset = float(offset.get("tilt", 0))

        try:
            zid = str(int(zone_id)) if zone_id is not None else None
        except Exception:
            zid = None
        overrides = cfg.get("zone_overrides", {}) or {}
        item = overrides.get(zid) if zid is not None else None
        if isinstance(item, dict) and bool(item.get("enabled", False)):
            pan = float(item.get("pan", 90)) + pan_offset
            tilt = float(item.get("tilt", 90)) + tilt_offset
            return {
                "valid": True,
                "pan": int(round(clamp(pan, pan_min, pan_max))),
                "tilt": int(round(clamp(tilt, tilt_min, tilt_max))),
                "mode": "zone_override",
                "map_name": str(item.get("name") or f"zone_{zid}"),
            }

        try:
            u = clamp(float(cx), 0.0, float(cfg.get("frame_width", STREAM_WIDTH)) - 1.0)
            v = clamp(float(cy), 0.0, float(cfg.get("frame_height", STREAM_HEIGHT)) - 1.0)
            grid = cfg.get("grid")
            if not isinstance(grid, list) or len(grid) < 2 or not all(isinstance(r, list) and len(r) >= 2 for r in grid):
                raise ValueError("invalid calibration grid")

            y_values = [float(row[0]["v"]) for row in grid]
            x_values = [float(p["u"]) for p in grid[0]]
            y0, y1, ty = self._find_interval(y_values, v)
            x0, x1, tx = self._find_interval(x_values, u)
            p00, p10 = grid[y0][x0], grid[y0][x1]
            p01, p11 = grid[y1][x0], grid[y1][x1]

            def bilinear(key):
                a = (1.0 - tx) * float(p00[key]) + tx * float(p10[key])
                b = (1.0 - tx) * float(p01[key]) + tx * float(p11[key])
                return (1.0 - ty) * a + ty * b

            pan = bilinear("pan") + pan_offset
            tilt = bilinear("tilt") + tilt_offset
            return {
                "valid": True,
                "pan": int(round(clamp(pan, pan_min, pan_max))),
                "tilt": int(round(clamp(tilt, tilt_min, tilt_max))),
                "mode": "grid_bilinear",
                "map_name": f"grid_{y0}{x0}_{y1}{x1}",
            }
        except Exception as e:
            return {
                "valid": False,
                "pan": 90,
                "tilt": 90,
                "mode": "invalid",
                "map_name": str(e),
            }


_mapper = ServoMapper()


def pixel_to_servo(cx, cy, zone_id=None):
    return _mapper.map(cx, cy, zone_id)


def reload_calibration():
    return _mapper.reload()


def get_calibration():
    return _mapper.snapshot()


def save_calibration(config: dict):
    return _mapper.save(config)


def limit_step(current, target, max_step):
    try:
        current = float(current)
        target = float(target)
        max_step = abs(float(max_step))
    except Exception:
        return int(round(float(target)))
    if max_step <= 0:
        return int(round(target))
    delta = target - current
    if delta > max_step:
        target = current + max_step
    elif delta < -max_step:
        target = current - max_step
    return int(round(target))
