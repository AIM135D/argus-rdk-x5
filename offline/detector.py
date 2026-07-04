# detector.py
# -*- coding: utf-8 -*-

import copy
import math
import time
from pathlib import Path

import cv2
import numpy as np
from hobot_dnn import pyeasy_dnn as dnn

from config import (
    CAPTURE_COOLDOWN_SECONDS,
    CLASS_NAMES,
    CLASSES_NUM,
    JPEG_QUALITY,
    LONG_DANGER_CAPTURE_SECONDS,
    MODEL_PATH,
    NMS_THRESHOLD,
    NMS_TOP_K,
    REG_MAX,
    SCORE_THRESHOLD,
    STRIDES,
)
from llm_bridge import get_llm_bridge
from state import add_event_log, get_current_danger_zone, state
from risk_engine import RiskEngine
from target_arbiter import TargetArbiter
from tracking_manager import TrackManager


RDK_COLORS = [
    (56, 56, 255), (151, 157, 255), (31, 112, 255), (29, 178, 255), (49, 210, 207),
    (10, 249, 72), (23, 204, 146), (134, 219, 61), (52, 147, 26), (187, 212, 0),
    (168, 153, 44), (255, 194, 0), (147, 69, 52), (255, 115, 100), (236, 24, 0),
    (255, 56, 132), (133, 0, 82), (255, 56, 203), (200, 149, 255), (199, 55, 255)
]

ENABLE_LOCAL_PREVIEW = True
LOCAL_PREVIEW_TITLE = "RDK X5 PPE Local Preview"


def draw_detection(img, bbox, score, class_id, color_override=None, extra_label=None):
    x1, y1, x2, y2 = bbox
    color = color_override if color_override is not None else RDK_COLORS[class_id % len(RDK_COLORS)]

    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

    name = CLASS_NAMES[class_id] if 0 <= class_id < len(CLASS_NAMES) else f"class_{class_id}"
    label = f"{name}: {score:.2f}"
    if extra_label:
        label = f"{label} | {extra_label}"

    (label_width, label_height), _ = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
    )
    label_x = x1
    label_y = y1 - 10 if y1 - 10 > label_height else y1 + 16

    cv2.rectangle(
        img,
        (label_x, label_y - label_height - 2),
        (label_x + label_width, label_y + 2),
        color,
        cv2.FILLED
    )
    cv2.putText(
        img,
        label,
        (label_x, label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        1,
        cv2.LINE_AA
    )


def softmax_np(x, axis=-1):
    x = x - np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x)
    return exp_x / np.sum(exp_x, axis=axis, keepdims=True)


def _safe_bool(v, default=True):
    if v is None:
        return default
    return bool(v)


def _risk_priority(risk_level: str):
    risk = str(risk_level or "high").lower()
    if risk == "high":
        return 3
    if risk == "medium":
        return 2
    return 1


def _risk_color(risk_level: str, active=False):
    risk = str(risk_level or "high").lower()
    if risk == "low":
        return (0, 215, 255) if active else (0, 180, 220)
    if risk == "medium":
        return (0, 140, 255) if active else (0, 110, 220)
    return (0, 0, 255) if active else (60, 60, 255)


def _ascii_zone_label(zone_item, stat, active=False):
    """Return an OpenCV-safe ASCII label for zone overlays.

    cv2.putText cannot render Chinese with the Hershey font, so drawing Chinese
    zone names such as "机械臂作业区" directly on frames will become "????".
    This helper keeps the original Chinese zone names in state/logs/frontend,
    but uses ASCII-only labels for the local OpenCV preview and video overlays.
    """
    try:
        zone_id = int(zone_item.get("id", 0))
    except Exception:
        zone_id = 0

    risk = str(zone_item.get("risk_level", "high") or "high").upper()
    rules = []
    if bool(zone_item.get("require_helmet", False)):
        rules.append("H")
    if bool(zone_item.get("require_vest", False)):
        rules.append("V")
    rule_text = "+".join(rules) if rules else "-"

    if not bool(zone_item.get("enabled", True)):
        return f"[OFF] Zone-{zone_id}"

    risk_text = ""
    if active:
        try:
            risk_score = float(stat.get("max_risk_score", 0.0))
        except Exception:
            risk_score = 0.0
        risk_text = f" R:{risk_score:.2f}"

    return f"[{risk}] Zone-{zone_id} PPE:{rule_text}{risk_text}"


def _normalize_zone_item_runtime(item, fallback_id=1):
    if not isinstance(item, dict):
        return {
            "id": int(fallback_id),
            "name": f"危险区{fallback_id}",
            "zone": get_current_danger_zone(),
            "risk_level": "high",
            "enabled": True,
            "require_helmet": False,
            "require_vest": False,
        }

    raw_zone = item.get("zone", get_current_danger_zone())
    if not isinstance(raw_zone, list) or len(raw_zone) != 4:
        raw_zone = get_current_danger_zone()

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

    enabled = _safe_bool(item.get("enabled", True), True)
    require_helmet = _safe_bool(item.get("require_helmet", False), False)
    require_vest = _safe_bool(item.get("require_vest", False), False)

    try:
        x1, y1, x2, y2 = [int(v) for v in raw_zone]
    except Exception:
        x1, y1, x2, y2 = get_current_danger_zone()

    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1

    return {
        "id": zone_id,
        "name": name,
        "zone": [x1, y1, x2, y2],
        "risk_level": risk_level,
        "enabled": enabled,
        "require_helmet": require_helmet,
        "require_vest": require_vest,
    }


def get_current_danger_zones_runtime():
    with state.lock:
        zones = copy.deepcopy(getattr(state, "danger_zones", None))

    if isinstance(zones, list) and len(zones) > 0:
        return [_normalize_zone_item_runtime(item, idx) for idx, item in enumerate(zones, start=1)]

    zone = get_current_danger_zone()
    return [{
        "id": 1,
        "name": "默认危险区",
        "zone": zone[:] if isinstance(zone, list) else [100, 100, 500, 400],
        "risk_level": "high",
        "enabled": True,
        "require_helmet": False,
        "require_vest": False,
    }]


def point_in_zone(cx, cy, zone):
    if not isinstance(zone, list) or len(zone) != 4:
        return False
    x1, y1, x2, y2 = zone
    return x1 < cx < x2 and y1 < cy < y2


def pick_top_risk_zone(enriched_zone_stats):
    active_zones = [z for z in enriched_zone_stats if z.get("active")]
    if not active_zones:
        return None

    active_zones.sort(
        key=lambda z: (
            _risk_priority(z.get("risk_level")),
            z.get("violation_person_count", 0),
            z.get("danger_person_count", 0),
            z.get("danger_duration", 0.0),
            -int(z.get("id", 0)),
        ),
        reverse=True
    )
    return active_zones[0]


def box_center(box):
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def center_in_person_region(person_box, item_box, kind):
    px1, py1, px2, py2 = person_box
    cx, cy = box_center(item_box)
    pw = max(1.0, px2 - px1)
    ph = max(1.0, py2 - py1)

    if kind == "helmet":
        return (
            (px1 - 0.10 * pw) <= cx <= (px2 + 0.10 * pw)
            and (py1 - 0.25 * ph) <= cy <= (py1 + 0.45 * ph)
        )

    if kind == "vest":
        return (
            (px1 - 0.05 * pw) <= cx <= (px2 + 0.05 * pw)
            and (py1 + 0.18 * ph) <= cy <= (py1 + 0.92 * ph)
        )

    return False


def associate_items_to_persons(persons, items, kind):
    assigned = {i: False for i in range(len(persons))}
    used_items = set()

    candidates = []
    for item_idx, item in enumerate(items):
        ibox = item["bbox"]
        icx, icy = box_center(ibox)

        for person_idx, person in enumerate(persons):
            pbox = person["bbox"]
            if not center_in_person_region(pbox, ibox, kind):
                continue

            px1, py1, px2, py2 = pbox
            pw = max(1.0, px2 - px1)
            ph = max(1.0, py2 - py1)

            if kind == "helmet":
                tx, ty = (px1 + px2) / 2.0, py1 + 0.18 * ph
            else:
                tx, ty = (px1 + px2) / 2.0, py1 + 0.52 * ph

            dist = math.hypot(icx - tx, icy - ty)
            norm_dist = dist / max(1.0, (pw + ph) / 2.0)
            candidates.append((norm_dist, item_idx, person_idx))

    candidates.sort(key=lambda x: x[0])

    used_person_item = set()
    for _, item_idx, person_idx in candidates:
        if item_idx in used_items:
            continue
        if (kind, person_idx) in used_person_item:
            continue
        assigned[person_idx] = True
        used_items.add(item_idx)
        used_person_item.add((kind, person_idx))

    return assigned


class UltralyticsYOLODetectBayeseYUV420SP:
    def __init__(self, model_path, classes_num, nms_thres, score_thres, reg, strides):
        model_file = Path(model_path)
        if not model_file.is_file():
            raise FileNotFoundError(
                f"ARGUS model not found: {model_file}. "
                "See models/README.md and set model_path in configs/runtime.yaml "
                "or ARGUS_MODEL_PATH."
            )
        self.quantize_model = dnn.load(str(model_file))

        print("✅ 已加载模型:", model_file)
        print("模型输入数:", len(self.quantize_model[0].inputs))
        print("模型输出数:", len(self.quantize_model[0].outputs))
        for i, out in enumerate(self.quantize_model[0].outputs):
            print(f"output[{i}] shape = {out.properties.shape}")

        self.REG = reg
        self.CLASSES_NUM = classes_num
        self.SCORE_THRESHOLD = score_thres
        self.NMS_THRESHOLD = nms_thres
        self.CONF_THRES_RAW = -np.log(1 / self.SCORE_THRESHOLD - 1)

        self.input_H, self.input_W = self.quantize_model[0].inputs[0].properties.shape[2:4]
        self.strides = strides

        if len(self.quantize_model[0].outputs) != 6:
            raise RuntimeError(
                f"当前模型输出数量不是 6，而是 {len(self.quantize_model[0].outputs)}。"
                " 这不是当前 PPE 6输出 DFL 模型。"
            )

        expected_shapes = [
            (1, 80, 80, self.CLASSES_NUM),
            (1, 80, 80, self.REG * 4),
            (1, 40, 40, self.CLASSES_NUM),
            (1, 40, 40, self.REG * 4),
            (1, 20, 20, self.CLASSES_NUM),
            (1, 20, 20, self.REG * 4),
        ]
        for i, out in enumerate(self.quantize_model[0].outputs):
            got = tuple(out.properties.shape)
            if got != expected_shapes[i]:
                raise RuntimeError(
                    f"output[{i}] shape 不匹配，got={got}, expected={expected_shapes[i]}"
                )

        self.weights_static = np.array(
            [i for i in range(reg)], dtype=np.float32
        )[np.newaxis, np.newaxis, :]

        self.grids = []
        for stride in self.strides:
            assert self.input_H % stride == 0
            assert self.input_W % stride == 0
            grid_h, grid_w = self.input_H // stride, self.input_W // stride

            gy, gx = np.meshgrid(
                np.arange(grid_h, dtype=np.float32) + 0.5,
                np.arange(grid_w, dtype=np.float32) + 0.5,
                indexing="ij"
            )
            grid = np.stack([gx, gy], axis=-1).reshape(-1, 2)
            self.grids.append(grid)

        self.img_h = None
        self.img_w = None
        self.x_scale = 1.0
        self.y_scale = 1.0
        self.x_shift = 0
        self.y_shift = 0

    def preprocess_yuv420sp(self, img):
        self.img_h, self.img_w = img.shape[:2]

        self.x_scale = min(1.0 * self.input_H / self.img_h, 1.0 * self.input_W / self.img_w)
        self.y_scale = self.x_scale

        if self.x_scale <= 0 or self.y_scale <= 0:
            raise ValueError("Invalid scale factor.")

        new_w = int(self.img_w * self.x_scale)
        self.x_shift = (self.input_W - new_w) // 2
        x_other = self.input_W - new_w - self.x_shift

        new_h = int(self.img_h * self.y_scale)
        self.y_shift = (self.input_H - new_h) // 2
        y_other = self.input_H - new_h - self.y_shift

        input_tensor = cv2.resize(img, (new_w, new_h))
        input_tensor = cv2.copyMakeBorder(
            input_tensor,
            self.y_shift, y_other, self.x_shift, x_other,
            cv2.BORDER_CONSTANT,
            value=[127, 127, 127]
        )
        input_tensor = self.bgr2nv12(input_tensor)
        return input_tensor

    def bgr2nv12(self, bgr_img):
        height, width = bgr_img.shape[:2]
        area = height * width
        yuv420p = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2YUV_I420).reshape((area * 3 // 2,))
        y = yuv420p[:area]
        uv_planar = yuv420p[area:].reshape((2, area // 4))
        uv_packed = uv_planar.transpose((1, 0)).reshape((area // 2,))
        nv12 = np.zeros_like(yuv420p)
        nv12[:area] = y
        nv12[area:] = uv_packed
        return nv12

    def forward(self, input_tensor):
        return self.quantize_model[0].forward(input_tensor)

    def c2numpy(self, outputs):
        return [dnn_tensor.buffer for dnn_tensor in outputs]

    def post_process(self, outputs):
        if len(outputs) != 6:
            raise RuntimeError(f"forward 实际返回 outputs 数量不是 6，而是 {len(outputs)}")

        clses = [
            outputs[0].reshape(-1, self.CLASSES_NUM),
            outputs[2].reshape(-1, self.CLASSES_NUM),
            outputs[4].reshape(-1, self.CLASSES_NUM),
        ]
        bboxes = [
            outputs[1].reshape(-1, self.REG * 4),
            outputs[3].reshape(-1, self.REG * 4),
            outputs[5].reshape(-1, self.REG * 4),
        ]

        dbboxes, ids, scores = [], [], []

        for cls, bbox, stride, grid in zip(clses, bboxes, self.strides, self.grids):
            max_scores = np.max(cls, axis=1)
            bbox_selected = np.flatnonzero(max_scores >= self.CONF_THRES_RAW)

            if bbox_selected.size == 0:
                continue

            ids.append(np.argmax(cls[bbox_selected, :], axis=1))
            scores.append(1 / (1 + np.exp(-max_scores[bbox_selected])))

            ltrb_selected = np.sum(
                softmax_np(
                    bbox[bbox_selected, :].reshape(-1, 4, self.REG),
                    axis=2
                ) * self.weights_static,
                axis=2
            )

            grid_selected = grid[bbox_selected, :]
            x1y1 = grid_selected - ltrb_selected[:, 0:2]
            x2y2 = grid_selected + ltrb_selected[:, 2:4]
            dbboxes.append(np.hstack([x1y1, x2y2]) * stride)

        if len(dbboxes) == 0:
            return []

        dbboxes = np.concatenate(dbboxes, axis=0)
        scores = np.concatenate(scores, axis=0)
        ids = np.concatenate(ids, axis=0)

        hw = dbboxes[:, 2:4] - dbboxes[:, 0:2]
        xywh = np.hstack([dbboxes[:, 0:2], hw])

        results = []
        for i in range(self.CLASSES_NUM):
            id_indices = ids == i
            if np.sum(id_indices) == 0:
                continue

            indices = cv2.dnn.NMSBoxes(
                xywh[id_indices, :].tolist(),
                scores[id_indices].tolist(),
                self.SCORE_THRESHOLD,
                self.NMS_THRESHOLD
            )

            if len(indices) == 0:
                continue

            picked = 0
            selected_boxes = dbboxes[id_indices, :]
            selected_scores = scores[id_indices]

            for indic in indices:
                if isinstance(indic, (list, tuple, np.ndarray)):
                    indic = int(indic[0])
                else:
                    indic = int(indic)

                x1, y1, x2, y2 = selected_boxes[indic]

                x1 = int((x1 - self.x_shift) / self.x_scale)
                y1 = int((y1 - self.y_shift) / self.y_scale)
                x2 = int((x2 - self.x_shift) / self.x_scale)
                y2 = int((y2 - self.y_shift) / self.y_scale)

                x1 = max(0, min(x1, self.img_w))
                x2 = max(0, min(x2, self.img_w))
                y1 = max(0, min(y1, self.img_h))
                y2 = max(0, min(y2, self.img_h))

                if x2 <= x1 or y2 <= y1:
                    continue

                results.append((i, float(selected_scores[indic]), x1, y1, x2, y2))
                picked += 1
                if NMS_TOP_K > 0 and picked >= NMS_TOP_K:
                    break

        return results


ppe_detector = UltralyticsYOLODetectBayeseYUV420SP(
    model_path=MODEL_PATH,
    classes_num=CLASSES_NUM,
    nms_thres=NMS_THRESHOLD,
    score_thres=SCORE_THRESHOLD,
    reg=REG_MAX,
    strides=STRIDES,
)


# 轻量跨帧状态、时空风险与多目标仲裁。
person_track_manager = TrackManager(frame_width=640, frame_height=360)
risk_engine = RiskEngine(duration_tau=2.2, point_mode="center", min_track_hits=2)
target_arbiter = TargetArbiter(frame_width=640, frame_height=360)

def draw_results(frame: np.ndarray, detections):
    """完成检测结果结构化、跨帧状态、风险评估与目标仲裁。"""
    draw_frame = frame.copy()
    now = time.time()

    people = []
    helmets = []
    vests = []
    for class_id, score, x1, y1, x2, y2 in detections:
        name = CLASS_NAMES[class_id] if 0 <= class_id < len(CLASS_NAMES) else f"class_{class_id}"
        obj = {
            "class_id": class_id,
            "score": float(score),
            "bbox": (x1, y1, x2, y2),
            "name": name,
        }
        if name == "person":
            people.append(obj)
        elif name == "helmet":
            helmets.append(obj)
        elif name == "reflective_vest":
            vests.append(obj)

    helmet_map = associate_items_to_persons(people, helmets, "helmet")
    vest_map = associate_items_to_persons(people, vests, "vest")

    observations = []
    for idx, person in enumerate(people):
        obs = dict(person)
        obs["has_helmet"] = bool(helmet_map.get(idx, False))
        obs["has_vest"] = bool(vest_map.get(idx, False))
        observations.append(obs)

    tracked_people = person_track_manager.update(observations, now=now)
    danger_zones = get_current_danger_zones_runtime()
    evaluated_tracks, risk_candidates = risk_engine.evaluate(tracked_people, danger_zones, now=now)
    selected_target = target_arbiter.select(risk_candidates, now=now)

    selected_target["track_count"] = len(evaluated_tracks)
    selected_target["risk_candidate_count"] = len(risk_candidates)
    selected_target["risk_candidates"] = [
        {
            "track_id": c.get("track_id"),
            "zone_id": c.get("target_zone_id"),
            "zone_name": c.get("target_zone_name"),
            "risk_score": round(float(c.get("risk_score", 0.0)), 3),
            "alarm_level": c.get("alarm_level", "none"),
            "reason": c.get("target_reason", "-"),
            "utility": round(float(c.get("target_utility", c.get("risk_score", 0.0))), 3),
        }
        for c in risk_candidates[:5]
    ]

    zone_stats = []
    zone_stat_by_id = {}
    for zone_item in danger_zones:
        item = {
            "id": zone_item["id"],
            "name": zone_item["name"],
            "risk_level": zone_item["risk_level"],
            "enabled": zone_item["enabled"],
            "require_helmet": zone_item["require_helmet"],
            "require_vest": zone_item["require_vest"],
            "current_person_count": 0,
            "danger_person_count": 0,
            "violation_person_count": 0,
            "missing_helmet_count": 0,
            "missing_vest_count": 0,
            "max_risk_score": 0.0,
            "active": False,
        }
        zone_stats.append(item)
        zone_stat_by_id[int(item["id"])] = item

    global_current_person_count = len(evaluated_tracks)
    global_danger_person_count = 0
    global_violation_count = 0
    global_missing_helmet_count = 0
    global_missing_vest_count = 0

    selected_track_id = selected_target.get("target_track_id")

    for track in evaluated_tracks:
        zone_evals = track.get("zone_evaluations", [])
        any_danger = False
        any_violation = False
        any_missing_helmet = False
        any_missing_vest = False
        for ze in zone_evals:
            stat = zone_stat_by_id.get(int(ze.get("zone_id", -1)))
            if stat is None:
                continue
            stat["current_person_count"] += 1
            if ze.get("missing_helmet"):
                stat["missing_helmet_count"] += 1
                any_missing_helmet = True
            if ze.get("missing_vest"):
                stat["missing_vest_count"] += 1
                any_missing_vest = True
            if ze.get("violation"):
                stat["violation_person_count"] += 1
                any_violation = True
            if ze.get("is_danger"):
                stat["danger_person_count"] += 1
                stat["active"] = True
                stat["max_risk_score"] = max(stat["max_risk_score"], float(ze.get("risk_score", 0.0)))
                any_danger = True

        global_danger_person_count += int(any_danger)
        global_violation_count += int(any_violation)
        global_missing_helmet_count += int(any_missing_helmet)
        global_missing_vest_count += int(any_missing_vest)

        bbox = track.get("smoothed_bbox") or track.get("bbox")
        score = float(track.get("score", 0.0))
        class_id = int(track.get("class_id", 0))
        risk_score = float(track.get("risk_score", 0.0))
        reason = str(track.get("risk_reason", "safe"))
        tid = int(track.get("track_id", -1))
        selected = selected_track_id is not None and int(selected_track_id) == tid

        if any_danger:
            color = (0, 0, 255) if track.get("alarm_level") == "high" else (0, 140, 255)
        elif track.get("in_zone"):
            color = (0, 215, 255)
        else:
            color = (0, 255, 0)

        label_parts = [f"ID:{tid}"]
        if any_danger:
            label_parts.append(f"R:{risk_score:.2f}")
            label_parts.append(reason)
        else:
            label_parts.append("SAFE")
        if selected:
            label_parts.append("LOCK")
            color = (255, 0, 255)

        draw_detection(
            draw_frame,
            bbox,
            score,
            class_id,
            color_override=color,
            extra_label=" | ".join(label_parts),
        )

        if selected:
            fx, fy = track.get("smoothed_foot") or box_center(bbox)
            cv2.circle(draw_frame, (int(round(fx)), int(round(fy))), 7, (255, 0, 255), -1)

    for item in helmets:
        draw_detection(draw_frame, item["bbox"], item["score"], item["class_id"])
    for item in vests:
        draw_detection(draw_frame, item["bbox"], item["score"], item["class_id"])

    for zone_item in danger_zones:
        zone = zone_item["zone"]
        stat = zone_stat_by_id.get(int(zone_item["id"]), {})
        active = bool(stat.get("active", False))
        color = _risk_color(zone_item["risk_level"], active=active)
        thickness = 3 if active else 2
        if not zone_item["enabled"]:
            color = (128, 128, 128)
        cv2.rectangle(draw_frame, (zone[0], zone[1]), (zone[2], zone[3]), color, thickness)

        rules = []
        if zone_item["require_helmet"]:
            rules.append("H")
        if zone_item["require_vest"]:
            rules.append("V")
        # Keep Chinese zone names in state/logs/frontend, but never draw them with
        # cv2.putText, because OpenCV Hershey fonts do not support Chinese.
        tag = _ascii_zone_label(zone_item, stat, active=active)
        cv2.putText(
            draw_frame,
            tag,
            (zone[0] + 5, max(20, zone[1] - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )

    danger_now = global_danger_person_count > 0
    return (
        draw_frame,
        danger_now,
        global_current_person_count,
        global_danger_person_count,
        global_violation_count,
        global_missing_helmet_count,
        global_missing_vest_count,
        zone_stats,
        selected_target,
    )

def handle_local_preview(frame: np.ndarray):
    global ENABLE_LOCAL_PREVIEW

    if not ENABLE_LOCAL_PREVIEW:
        return

    try:
        cv2.imshow(LOCAL_PREVIEW_TITLE, frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            try:
                cv2.destroyWindow(LOCAL_PREVIEW_TITLE)
            except Exception:
                pass
            ENABLE_LOCAL_PREVIEW = False
            print("🖥️ 本地预览窗口已关闭，Web 监控继续运行")
    except Exception as e:
        ENABLE_LOCAL_PREVIEW = False
        print(f"⚠️ 本地预览不可用，已自动关闭本地窗口模式: {e}")


def has_ws_frame_clients():
    try:
        with state.lock:
            return len(state.clients) > 0
    except Exception:
        return False


def inference_loop():
    prev_stat_time = time.time()
    frame_count = 0
    last_processed_seq = -1

    while state.running:
        with state.frame_lock:
            if state.latest_frame is None or state.latest_frame_seq == last_processed_seq:
                frame = None
                frame_seq = last_processed_seq
            else:
                frame = state.latest_frame.copy()
                frame_seq = state.latest_frame_seq

        if frame is None:
            time.sleep(0.001)
            continue

        last_processed_seq = frame_seq
        t0 = time.time()

        try:
            input_tensor = ppe_detector.preprocess_yuv420sp(frame)
            outputs = ppe_detector.c2numpy(ppe_detector.forward(input_tensor))
            detections = ppe_detector.post_process(outputs)

            (
                draw_frame,
                danger_now,
                current_person_count,
                danger_person_count,
                ppe_violation_count,
                missing_helmet_count,
                missing_vest_count,
                zone_stats,
                esp32_target,
            ) = draw_results(frame, detections)

            handle_local_preview(draw_frame)

            now = time.time()
            edge_alerts = []
            auto_captures = []
            enriched_zone_stats = []

            with state.lock:
                for zone_stat in zone_stats:
                    zone_id = int(zone_stat["id"])
                    if zone_id not in state.zone_runtime:
                        state.zone_runtime[zone_id] = {
                            "id": zone_id,
                            "name": zone_stat["name"],
                            "risk_level": zone_stat.get("risk_level", "high"),
                            "enabled": bool(zone_stat.get("enabled", True)),
                            "require_helmet": bool(zone_stat.get("require_helmet", False)),
                            "require_vest": bool(zone_stat.get("require_vest", False)),
                            "active": False,
                            "danger_start_time": None,
                            "danger_duration": 0.0,
                            "danger_count": 0,
                            "last_capture_time": 0.0,
                            "last_alert": "-",
                        }

                    rt = state.zone_runtime[zone_id]
                    prev_active = bool(rt.get("active", False))
                    now_active = bool(zone_stat.get("danger_person_count", 0) > 0)

                    rt["name"] = zone_stat["name"]
                    rt["risk_level"] = zone_stat.get("risk_level", "high")
                    rt["enabled"] = bool(zone_stat.get("enabled", True))
                    rt["require_helmet"] = bool(zone_stat.get("require_helmet", False))
                    rt["require_vest"] = bool(zone_stat.get("require_vest", False))

                    if now_active:
                        if rt["danger_start_time"] is None:
                            rt["danger_start_time"] = now
                        rt["danger_duration"] = round(now - rt["danger_start_time"], 1)
                    else:
                        rt["danger_start_time"] = None
                        rt["danger_duration"] = 0.0

                    if now_active and not prev_active:
                        rt["danger_count"] += 1
                        rt["last_alert"] = time.strftime("%H:%M:%S")
                        edge_alerts.append({
                            "id": zone_id,
                            "name": rt["name"],
                            "risk_level": rt["risk_level"],
                            "danger_count": rt["danger_count"],
                            "last_alert": rt["last_alert"],
                            "missing_helmet_count": zone_stat["missing_helmet_count"],
                            "missing_vest_count": zone_stat["missing_vest_count"],
                            "violation_person_count": zone_stat["violation_person_count"],
                        })

                    if now_active and rt["danger_duration"] >= LONG_DANGER_CAPTURE_SECONDS:
                        if now - rt["last_capture_time"] >= CAPTURE_COOLDOWN_SECONDS:
                            rt["last_capture_time"] = now
                            auto_captures.append({
                                "id": zone_id,
                                "name": rt["name"],
                                "risk_level": rt["risk_level"],
                                "danger_duration": rt["danger_duration"],
                            })

                    rt["active"] = now_active

                    enriched_zone_stats.append({
                        **zone_stat,
                        "active": now_active,
                        "danger_duration": rt["danger_duration"],
                        "danger_count": rt["danger_count"],
                        "last_alert": rt["last_alert"],
                    })

                active_zone_names = [z["name"] for z in enriched_zone_stats if z["active"]]
                top_zone = pick_top_risk_zone(enriched_zone_stats)
                top_risk_zone_name = top_zone["name"] if top_zone else "-"
                global_danger_duration = max(
                    [z["danger_duration"] for z in enriched_zone_stats if z["active"]],
                    default=0.0
                )

            for item in edge_alerts:
                reason_parts = []
                if item["missing_helmet_count"] > 0:
                    reason_parts.append("未戴安全帽")
                if item["missing_vest_count"] > 0:
                    reason_parts.append("未穿反光衣")

                if reason_parts:
                    alert_message = f"{time.strftime('%H:%M:%S')} 检测到目标进入{item['name']}（{'、'.join(reason_parts)}）"
                else:
                    alert_message = f"{time.strftime('%H:%M:%S')} 检测到目标进入{item['name']}"

                print(f"🚨 危险！{alert_message}")
                log_id = add_event_log(
                    "alert",
                    alert_message,
                    extra={
                        "zone_id": item["id"],
                        "zone_name": item["name"],
                        "risk_level": item["risk_level"],
                        "danger_count": item["danger_count"],
                        "violation_person_count": item["violation_person_count"],
                        "missing_helmet_count": item["missing_helmet_count"],
                        "missing_vest_count": item["missing_vest_count"],
                        "active_zone_names": active_zone_names,
                        "zone_stats": enriched_zone_stats,
                    }
                )

                get_llm_bridge().submit_event(
                    log_id,
                    {
                        "type": "alert",
                        "message": alert_message,
                        "zone_id": item["id"],
                        "zone_name": item["name"],
                        "risk_level": item["risk_level"],
                        "danger_count": item["danger_count"],
                        "violation_person_count": item["violation_person_count"],
                        "missing_helmet_count": item["missing_helmet_count"],
                        "missing_vest_count": item["missing_vest_count"],
                    }
                )

            for item in auto_captures:
                capture_message = (
                    f"{time.strftime('%H:%M:%S')} {item['name']} 持续危险 "
                    f"{item['danger_duration']:.1f}s，系统已自动抓拍"
                )
                print(f"📸 {capture_message}")
                log_id = add_event_log(
                    "auto_capture",
                    capture_message,
                    draw_frame,
                    extra={
                        "zone_id": item["id"],
                        "zone_name": item["name"],
                        "risk_level": item["risk_level"],
                        "danger_duration": item["danger_duration"],
                        "active_zone_names": active_zone_names,
                        "zone_stats": enriched_zone_stats,
                    }
                )

                get_llm_bridge().submit_event(
                    log_id,
                    {
                        "type": "auto_capture",
                        "message": capture_message,
                        "zone_id": item["id"],
                        "zone_name": item["name"],
                        "risk_level": item["risk_level"],
                        "danger_duration": item["danger_duration"],
                    }
                )

            need_ws_frame = has_ws_frame_clients()
            frame_bytes = None

            if need_ws_frame:
                ok, buffer = cv2.imencode(
                    ".jpg",
                    draw_frame,
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                )
                if ok:
                    frame_bytes = buffer.tobytes()

            t1 = time.time()
            infer_ms = (t1 - t0) * 1000.0

            frame_count += 1
            if t1 - prev_stat_time >= 1.0:
                fps = frame_count / (t1 - prev_stat_time)
                frame_count = 0
                prev_stat_time = t1
            else:
                with state.lock:
                    fps = state.latest_info["fps"]

            total_edge_alerts = len(edge_alerts)

            with state.lock:
                state.prev_danger = danger_now
                state.latest_jpeg = frame_bytes if need_ws_frame else None
                state.latest_info["fps"] = fps
                state.latest_info["infer_ms"] = infer_ms
                state.latest_info["danger"] = danger_now
                state.latest_info["frame_id"] += 1
                state.latest_info["current_person_count"] = current_person_count
                state.latest_info["danger_person_count"] = danger_person_count
                state.latest_info["danger_duration"] = round(global_danger_duration, 1)

                state.latest_info["ppe_violation_count"] = ppe_violation_count
                state.latest_info["missing_helmet_count"] = missing_helmet_count
                state.latest_info["missing_vest_count"] = missing_vest_count

                state.latest_info["zone_stats"] = enriched_zone_stats
                state.latest_info["active_zone_names"] = active_zone_names
                state.latest_info["top_risk_zone_name"] = top_risk_zone_name

                # 风险引擎和仲裁器已经完成跨帧状态、锁定、抢占与短时丢失保持。
                state.latest_info.update(esp32_target)
                state.latest_info["target_raw_valid"] = bool(esp32_target.get("target_valid", False))
                state.latest_info["target_raw_reason"] = esp32_target.get("target_reason", "-")
                state.latest_info["track_count"] = int(esp32_target.get("track_count", current_person_count))
                state.latest_info["risk_candidate_count"] = int(esp32_target.get("risk_candidate_count", 0))
                state.latest_info["risk_candidates"] = esp32_target.get("risk_candidates", [])

                if total_edge_alerts > 0:
                    state.latest_info["danger_count"] += total_edge_alerts
                    state.latest_info["last_alert"] = time.strftime("%H:%M:%S")

        except Exception as e:
            print("推理线程异常:", repr(e))
            time.sleep(0.002)

    if ENABLE_LOCAL_PREVIEW:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
