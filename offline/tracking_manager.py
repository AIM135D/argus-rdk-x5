# -*- coding: utf-8 -*-
"""轻量级 tracking-by-detection 人员轨迹管理。

不依赖 scipy / ByteTrack / DeepSORT，适合当前 RDK X5 离线环境。
目标不是做通用 MOT 榜单，而是为风险持续时间、PPE 时序投票、
目标锁定与舵机仲裁提供稳定 track_id。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


BBox = Tuple[float, float, float, float]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def bbox_center(box: BBox) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) * 0.5, (y1 + y2) * 0.5


def bbox_foot(box: BBox) -> Tuple[float, float]:
    x1, _, x2, y2 = box
    return (x1 + x2) * 0.5, y2


def bbox_iou(a: BBox, b: BBox) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    return inter / max(1.0, area_a + area_b - inter)


@dataclass
class _Track:
    track_id: int
    bbox: BBox
    smoothed_bbox: BBox
    score: float
    helmet_prob: float
    vest_prob: float
    first_seen: float
    last_seen: float
    prev_center: Tuple[float, float]
    center: Tuple[float, float]
    velocity: Tuple[float, float] = (0.0, 0.0)
    age_frames: int = 1
    hits: int = 1
    missed: int = 0
    metadata: dict = field(default_factory=dict)


class TrackManager:
    def __init__(
        self,
        frame_width: int = 640,
        frame_height: int = 360,
        max_missed: int = 8,
        min_iou: float = 0.05,
        max_center_distance_ratio: float = 0.22,
        bbox_smooth_alpha: float = 0.62,
        ppe_ema_alpha: float = 0.42,
        ppe_positive_threshold: float = 0.56,
    ):
        self.frame_width = int(frame_width)
        self.frame_height = int(frame_height)
        self.max_missed = int(max_missed)
        self.min_iou = float(min_iou)
        self.max_center_distance_ratio = float(max_center_distance_ratio)
        self.bbox_smooth_alpha = float(bbox_smooth_alpha)
        self.ppe_ema_alpha = float(ppe_ema_alpha)
        self.ppe_positive_threshold = float(ppe_positive_threshold)
        self._tracks: Dict[int, _Track] = {}
        self._next_id = 1

    @property
    def active_track_count(self) -> int:
        return len(self._tracks)

    def _new_track(self, obs: dict, now: float) -> _Track:
        bbox = tuple(float(v) for v in obs["bbox"])
        center = bbox_center(bbox)
        track = _Track(
            track_id=self._next_id,
            bbox=bbox,
            smoothed_bbox=bbox,
            score=float(obs.get("score", 0.0)),
            helmet_prob=1.0 if bool(obs.get("has_helmet", False)) else 0.0,
            vest_prob=1.0 if bool(obs.get("has_vest", False)) else 0.0,
            first_seen=now,
            last_seen=now,
            prev_center=center,
            center=center,
        )
        self._next_id += 1
        return track

    def _match_cost(self, track: _Track, obs: dict) -> Tuple[float, float, float]:
        bbox = tuple(float(v) for v in obs["bbox"])
        iou = bbox_iou(track.bbox, bbox)
        tcx, tcy = track.center
        ocx, ocy = bbox_center(bbox)
        diag = max(1.0, math.hypot(self.frame_width, self.frame_height))
        dist_ratio = math.hypot(ocx - tcx, ocy - tcy) / diag
        # 越小越好。IoU 优先，中心距离用于遮挡/框波动时兜底。
        cost = (1.0 - iou) * 0.68 + dist_ratio * 1.35
        return cost, iou, dist_ratio

    def update(self, observations: List[dict], now: float | None = None) -> List[dict]:
        now = float(now if now is not None else time.time())
        observations = [dict(o) for o in observations]

        track_ids = list(self._tracks.keys())
        pairs = []
        for track_id in track_ids:
            track = self._tracks[track_id]
            for obs_idx, obs in enumerate(observations):
                cost, iou, dist_ratio = self._match_cost(track, obs)
                if iou >= self.min_iou or dist_ratio <= self.max_center_distance_ratio:
                    pairs.append((cost, track_id, obs_idx, iou, dist_ratio))
        pairs.sort(key=lambda x: x[0])

        matched_tracks = set()
        matched_obs = set()
        assignments = {}
        for _, track_id, obs_idx, _, _ in pairs:
            if track_id in matched_tracks or obs_idx in matched_obs:
                continue
            matched_tracks.add(track_id)
            matched_obs.add(obs_idx)
            assignments[obs_idx] = track_id

        # 未匹配轨迹记 miss。
        for track_id, track in list(self._tracks.items()):
            if track_id not in matched_tracks:
                track.missed += 1
                track.age_frames += 1
                if track.missed > self.max_missed:
                    del self._tracks[track_id]

        outputs = []
        for obs_idx, obs in enumerate(observations):
            if obs_idx not in assignments:
                track = self._new_track(obs, now)
                self._tracks[track.track_id] = track
            else:
                track = self._tracks[assignments[obs_idx]]
                new_bbox = tuple(float(v) for v in obs["bbox"])
                alpha = _clamp(self.bbox_smooth_alpha, 0.0, 1.0)
                old_s = track.smoothed_bbox
                smooth = tuple(alpha * n + (1.0 - alpha) * o for n, o in zip(new_bbox, old_s))

                old_center = track.center
                new_center = bbox_center(smooth)
                dt = max(1e-3, now - track.last_seen)
                raw_vx = (new_center[0] - old_center[0]) / dt
                raw_vy = (new_center[1] - old_center[1]) / dt
                track.velocity = (
                    0.55 * raw_vx + 0.45 * track.velocity[0],
                    0.55 * raw_vy + 0.45 * track.velocity[1],
                )
                track.prev_center = old_center
                track.center = new_center
                track.bbox = new_bbox
                track.smoothed_bbox = smooth
                track.score = float(obs.get("score", 0.0))
                track.last_seen = now
                track.age_frames += 1
                track.hits += 1
                track.missed = 0

                ppe_alpha = _clamp(self.ppe_ema_alpha, 0.0, 1.0)
                helmet_now = 1.0 if bool(obs.get("has_helmet", False)) else 0.0
                vest_now = 1.0 if bool(obs.get("has_vest", False)) else 0.0
                track.helmet_prob = ppe_alpha * helmet_now + (1.0 - ppe_alpha) * track.helmet_prob
                track.vest_prob = ppe_alpha * vest_now + (1.0 - ppe_alpha) * track.vest_prob

            sx1, sy1, sx2, sy2 = track.smoothed_bbox
            scx, scy = bbox_center(track.smoothed_bbox)
            sfx, sfy = bbox_foot(track.smoothed_bbox)
            out = dict(obs)
            out.update({
                "track_id": int(track.track_id),
                "track_age_frames": int(track.age_frames),
                "track_hits": int(track.hits),
                "track_duration": round(max(0.0, now - track.first_seen), 3),
                "smoothed_bbox": (
                    int(round(sx1)), int(round(sy1)), int(round(sx2)), int(round(sy2))
                ),
                "smoothed_center": (float(scx), float(scy)),
                "smoothed_foot": (float(sfx), float(sfy)),
                "velocity_x": float(track.velocity[0]),
                "velocity_y": float(track.velocity[1]),
                "helmet_prob": round(float(track.helmet_prob), 4),
                "vest_prob": round(float(track.vest_prob), 4),
                "has_helmet_stable": bool(track.helmet_prob >= self.ppe_positive_threshold),
                "has_vest_stable": bool(track.vest_prob >= self.ppe_positive_threshold),
            })
            outputs.append(out)

        return outputs
