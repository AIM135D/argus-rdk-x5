# -*- coding: utf-8 -*-
"""多目标风险仲裁器。

在同一时刻只有一个指向执行器时，综合风险、当前锁定奖励、
切换代价和转动距离选择目标，并提供抢占/滞回/短时丢失保持。
"""

from __future__ import annotations

import math
import time
from typing import Dict, List


class TargetArbiter:
    def __init__(
        self,
        frame_width: int = 640,
        frame_height: int = 360,
        lock_bonus: float = 0.07,
        switch_penalty: float = 0.04,
        rotation_weight: float = 0.03,
        preempt_margin: float = 0.06,
        lost_hold_seconds: float = 0.75,
    ):
        self.frame_width = int(frame_width)
        self.frame_height = int(frame_height)
        self.lock_bonus = float(lock_bonus)
        self.switch_penalty = float(switch_penalty)
        self.rotation_weight = float(rotation_weight)
        self.preempt_margin = float(preempt_margin)
        self.lost_hold_seconds = float(lost_hold_seconds)
        self.current: Dict | None = None
        self.last_seen_time = 0.0
        self.switch_count = 0
        self.last_switch_reason = "init"

    def _rotation_cost(self, candidate: dict) -> float:
        if self.current is None:
            return 0.0
        dx = float(candidate.get("target_x", 0)) - float(self.current.get("target_x", 0))
        dy = float(candidate.get("target_y", 0)) - float(self.current.get("target_y", 0))
        diag = max(1.0, math.hypot(self.frame_width, self.frame_height))
        return min(1.0, math.hypot(dx, dy) / diag) * self.rotation_weight

    def _utility(self, candidate: dict) -> float:
        utility = float(candidate.get("risk_score", 0.0))
        same_track = self.current is not None and int(candidate.get("track_id", -1)) == int(self.current.get("track_id", -2))
        if same_track:
            utility += self.lock_bonus
        elif self.current is not None:
            utility -= self.switch_penalty
        utility -= self._rotation_cost(candidate)
        # 持续事件略微优先，但限制上限，避免时间完全压过风险等级。
        utility += min(0.04, float(candidate.get("danger_duration", 0.0)) * 0.008)
        return utility

    def _empty(self, reason: str = "lost") -> dict:
        return {
            "target_valid": False,
            "track_id": None,
            "target_track_id": None,
            "target_x": -1,
            "target_y": -1,
            "target_conf": 0.0,
            "target_zone_id": None,
            "target_zone_name": "-",
            "target_reason": reason,
            "target_point_type": "none",
            "target_priority": 0,
            "risk_score": 0.0,
            "alarm_level": "none",
            "target_hold": False,
            "target_preempted": False,
            "target_utility": 0.0,
            "target_switch_count": int(self.switch_count),
            "target_switch_reason": self.last_switch_reason,
        }

    def select(self, candidates: List[dict], now: float | None = None) -> dict:
        now = float(now if now is not None else time.time())
        ready = [dict(c) for c in candidates if c.get("target_valid") and c.get("candidate_ready", True)]
        for c in ready:
            c["target_utility"] = round(self._utility(c), 4)

        current_candidate = None
        if self.current is not None:
            for c in ready:
                if int(c.get("track_id", -1)) == int(self.current.get("track_id", -2)):
                    current_candidate = c
                    break

        if current_candidate is not None:
            self.last_seen_time = now
            best = max(ready, key=lambda c: c["target_utility"]) if ready else current_candidate
            if int(best.get("track_id", -1)) != int(current_candidate.get("track_id", -2)):
                if float(best["target_utility"]) > float(current_candidate["target_utility"]) + self.preempt_margin:
                    best["target_preempted"] = True
                    best["target_hold"] = False
                    self.switch_count += 1
                    self.last_switch_reason = "higher_risk_preempt"
                    self.current = dict(best)
                else:
                    current_candidate["target_preempted"] = False
                    current_candidate["target_hold"] = False
                    self.current = dict(current_candidate)
            else:
                best["target_preempted"] = False
                best["target_hold"] = False
                self.current = dict(best)
        elif ready:
            best = max(ready, key=lambda c: c["target_utility"])
            previous_id = None if self.current is None else self.current.get("track_id")
            best["target_preempted"] = bool(previous_id is not None)
            best["target_hold"] = False
            if previous_id is not None and int(previous_id) != int(best.get("track_id", -1)):
                self.switch_count += 1
                self.last_switch_reason = "current_lost_switch"
            else:
                self.last_switch_reason = "acquire"
            self.current = dict(best)
            self.last_seen_time = now
        elif self.current is not None and now - self.last_seen_time <= self.lost_hold_seconds:
            hold = dict(self.current)
            hold["target_valid"] = True
            hold["target_hold"] = True
            hold["target_preempted"] = False
            reason = str(hold.get("target_reason") or "risk")
            if "lost_hold" not in reason:
                reason += "/lost_hold"
            hold["target_reason"] = reason
            hold["alarm_level"] = "none"  # 丢失保持期间只保持方向，不延长报警。
            hold["risk_score"] = 0.0
            self.current = dict(hold)
        else:
            self.current = None
            return self._empty("lost")

        out = dict(self.current)
        out["target_track_id"] = out.get("track_id")
        out["target_priority"] = int(round(float(out.get("risk_score", 0.0)) * 1000.0))
        out["target_switch_count"] = int(self.switch_count)
        out["target_switch_reason"] = self.last_switch_reason
        return out
