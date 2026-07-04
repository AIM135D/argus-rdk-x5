# -*- coding: utf-8 -*-
"""时空风险评估引擎。

融合危险区等级、PPE 状态、持续时间、运动趋势与感知不确定性。
输出的是可解释风险候选，而不是直接控制硬件。
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Tuple


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def point_in_rect(x: float, y: float, zone: list) -> bool:
    if not isinstance(zone, list) or len(zone) != 4:
        return False
    x1, y1, x2, y2 = zone
    return float(x1) < x < float(x2) and float(y1) < y < float(y2)


def risk_priority(level: str) -> int:
    level = str(level or "low").lower()
    return {"low": 1, "medium": 2, "high": 3}.get(level, 1)


class RiskEngine:
    def __init__(
        self,
        duration_tau: float = 2.2,
        point_mode: str = "center",
        min_track_hits: int = 2,
    ):
        self.duration_tau = max(0.2, float(duration_tau))
        self.point_mode = str(point_mode or "center")
        self.min_track_hits = max(1, int(min_track_hits))
        self._active_since: Dict[Tuple[int, int], float] = {}
        self._event_history: Dict[Tuple[int, int], int] = {}
        self._last_seen_key: Dict[Tuple[int, int], float] = {}
        self._last_active_keys = set()
        self.release_grace_seconds = 0.55

    def _point_for_zone(self, track: dict) -> Tuple[float, float]:
        if self.point_mode == "foot":
            return tuple(track.get("smoothed_foot") or track.get("center") or (0.0, 0.0))
        return tuple(track.get("smoothed_center") or track.get("center") or (0.0, 0.0))

    def _approach_score(self, track: dict, zone: list) -> float:
        try:
            x1, y1, x2, y2 = [float(v) for v in zone]
            zcx, zcy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
            cx, cy = track.get("smoothed_center") or (0.0, 0.0)
            vx = float(track.get("velocity_x", 0.0))
            vy = float(track.get("velocity_y", 0.0))
            dx, dy = zcx - float(cx), zcy - float(cy)
            norm = max(1.0, math.hypot(dx, dy))
            toward_speed = (vx * dx + vy * dy) / norm
            return clamp(toward_speed / 180.0)
        except Exception:
            return 0.0

    def _uncertainty(self, track: dict, require_helmet: bool, require_vest: bool) -> float:
        score = clamp(track.get("score", 0.0))
        uncertainty = (1.0 - score) * 0.55
        if require_helmet:
            hp = clamp(track.get("helmet_prob", 0.5))
            uncertainty += (1.0 - abs(hp - 0.5) * 2.0) * 0.24
        if require_vest:
            vp = clamp(track.get("vest_prob", 0.5))
            uncertainty += (1.0 - abs(vp - 0.5) * 2.0) * 0.21
        return clamp(uncertainty)

    def _score(self, zone: dict, missing_helmet: bool, missing_vest: bool,
               duration: float, motion: float, uncertainty: float, history_count: int) -> float:
        zone_base = {"high": 0.53, "medium": 0.36, "low": 0.22}.get(
            str(zone.get("risk_level", "low")).lower(), 0.22
        )
        ppe = 0.0
        if missing_helmet:
            ppe += 0.20
        if missing_vest:
            ppe += 0.12
        if missing_helmet and missing_vest:
            ppe += 0.05
        duration_term = 0.15 * (1.0 - math.exp(-max(0.0, duration) / self.duration_tau))
        motion_term = 0.07 * clamp(motion)
        history_term = min(0.04, max(0, int(history_count)) * 0.01)
        uncertainty_penalty = 0.10 * clamp(uncertainty)
        return clamp(zone_base + ppe + duration_term + motion_term + history_term - uncertainty_penalty)

    @staticmethod
    def _level(score: float, zone_level: str) -> str:
        # 动态分数决定报警强度，同时避免高风险区被过度降级。
        if score >= 0.76:
            level = "high"
        elif score >= 0.48:
            level = "medium"
        else:
            level = "low"
        if risk_priority(zone_level) == 3 and score >= 0.62:
            level = "high"
        return level

    def evaluate(self, tracks: List[dict], zones: List[dict], now: float | None = None):
        now = float(now if now is not None else time.time())
        current_keys = set()
        evaluated_tracks = []
        candidates = []

        for track in tracks:
            tx, ty = self._point_for_zone(track)
            zone_evals = []
            best = None

            for zone in zones:
                if not bool(zone.get("enabled", True)):
                    continue
                if not point_in_rect(tx, ty, zone.get("zone")):
                    continue

                zone_id = int(zone.get("id", 0))
                track_id = int(track.get("track_id", -1))
                key = (track_id, zone_id)
                current_keys.add(key)
                self._last_seen_key[key] = now
                if key not in self._active_since:
                    self._active_since[key] = now
                    self._event_history[key] = self._event_history.get(key, 0) + 1
                duration = max(0.0, now - self._active_since[key])

                has_helmet = bool(track.get("has_helmet_stable", track.get("has_helmet", False)))
                has_vest = bool(track.get("has_vest_stable", track.get("has_vest", False)))
                require_helmet = bool(zone.get("require_helmet", False))
                require_vest = bool(zone.get("require_vest", False))
                missing_helmet = require_helmet and not has_helmet
                missing_vest = require_vest and not has_vest
                has_ppe_rule = require_helmet or require_vest
                violation = missing_helmet or missing_vest
                is_danger = violation if has_ppe_rule else True

                reasons = []
                if missing_helmet:
                    reasons.append("missing_helmet")
                if missing_vest:
                    reasons.append("missing_vest")
                if not reasons and is_danger:
                    reasons.append("zone_intrusion")

                motion = self._approach_score(track, zone)
                uncertainty = self._uncertainty(track, require_helmet, require_vest)
                score = self._score(
                    zone, missing_helmet, missing_vest, duration,
                    motion, uncertainty, self._event_history.get(key, 0)
                ) if is_danger else 0.0
                level = self._level(score, str(zone.get("risk_level", "low"))) if is_danger else "none"

                item = {
                    "zone_id": zone_id,
                    "zone_name": str(zone.get("name") or f"区域{zone_id}"),
                    "zone_risk_level": str(zone.get("risk_level", "low")),
                    "zone": list(zone.get("zone") or []),
                    "require_helmet": require_helmet,
                    "require_vest": require_vest,
                    "missing_helmet": bool(missing_helmet),
                    "missing_vest": bool(missing_vest),
                    "violation": bool(violation),
                    "is_danger": bool(is_danger),
                    "duration": round(duration, 3),
                    "motion_score": round(motion, 4),
                    "uncertainty": round(uncertainty, 4),
                    "risk_score": round(score, 4),
                    "alarm_level": level,
                    "reasons": reasons,
                }
                zone_evals.append(item)

                if is_danger:
                    key_rank = (
                        float(score),
                        risk_priority(zone.get("risk_level")),
                        int(violation),
                        int(missing_helmet) + int(missing_vest),
                    )
                    if best is None or key_rank > best[0]:
                        best = (key_rank, item)

            enriched = dict(track)
            enriched["zone_evaluations"] = zone_evals
            enriched["in_zone"] = bool(zone_evals)
            enriched["is_danger"] = bool(best is not None)

            if best is not None:
                best_zone = best[1]
                foot_x, foot_y = track.get("smoothed_foot") or (tx, ty)
                candidate = {
                    "track_id": int(track.get("track_id", -1)),
                    "target_valid": True,
                    "target_x": int(round(float(foot_x))),
                    "target_y": int(round(float(foot_y))),
                    "target_conf": round(float(track.get("score", 0.0)), 4),
                    "target_zone_id": int(best_zone["zone_id"]),
                    "target_zone_name": best_zone["zone_name"],
                    "target_reason": "/".join(best_zone["reasons"]) or "zone_intrusion",
                    "target_point_type": "smoothed_foot",
                    "risk_score": float(best_zone["risk_score"]),
                    "alarm_level": best_zone["alarm_level"],
                    "zone_risk_level": best_zone["zone_risk_level"],
                    "danger_duration": float(best_zone["duration"]),
                    "motion_score": float(best_zone["motion_score"]),
                    "uncertainty": float(best_zone["uncertainty"]),
                    "missing_helmet": bool(best_zone["missing_helmet"]),
                    "missing_vest": bool(best_zone["missing_vest"]),
                    "track_age_frames": int(track.get("track_age_frames", 0)),
                    "track_hits": int(track.get("track_hits", 0)),
                }
                # 极高风险允许更快确认；一般候选至少经历若干帧。
                candidate["candidate_ready"] = bool(
                    candidate["track_hits"] >= self.min_track_hits or candidate["risk_score"] >= 0.86
                )
                candidates.append(candidate)
                enriched.update({
                    "risk_score": candidate["risk_score"],
                    "alarm_level": candidate["alarm_level"],
                    "best_zone_id": candidate["target_zone_id"],
                    "best_zone_name": candidate["target_zone_name"],
                    "risk_reason": candidate["target_reason"],
                    "danger_duration": candidate["danger_duration"],
                })
            else:
                enriched.update({
                    "risk_score": 0.0,
                    "alarm_level": "none",
                    "best_zone_id": None,
                    "best_zone_name": "-",
                    "risk_reason": "safe",
                    "danger_duration": 0.0,
                })

            evaluated_tracks.append(enriched)

        # 短暂漏检不立刻清零持续时间，超过宽限期才释放。
        for key in list(self._active_since.keys()):
            if key not in current_keys:
                last_seen = self._last_seen_key.get(key, 0.0)
                if now - last_seen > self.release_grace_seconds:
                    del self._active_since[key]
                    self._last_seen_key.pop(key, None)
        self._last_active_keys = current_keys

        candidates.sort(key=lambda c: (c["risk_score"], c["danger_duration"], c["target_conf"]), reverse=True)
        return evaluated_tracks, candidates
