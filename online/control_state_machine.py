# -*- coding: utf-8 -*-
"""主动定向预警控制状态机。

状态：IDLE -> AIMING -> ALARMING -> HOLDING / PREEMPTING -> RECOVERING。
仅决定执行节奏和蜂鸣器等级，不参与感知与风险计算。
"""

from __future__ import annotations

import time


class ControlStateMachine:
    def __init__(
        self,
        aiming_seconds: float = 0.30,
        recover_seconds: float = 0.45,
    ):
        self.aiming_seconds = max(0.0, float(aiming_seconds))
        self.recover_seconds = max(0.0, float(recover_seconds))
        self.state = "IDLE"
        self.state_since = time.time()
        self.current_track_id = None

    @staticmethod
    def alarm_to_beep(level: str) -> int:
        level = str(level or "none").lower()
        if level == "high":
            return 3
        if level == "medium":
            return 2
        if level == "low":
            return 1
        return 0

    def _set(self, state: str, now: float):
        if state != self.state:
            self.state = state
            self.state_since = now

    def update(self, target: dict, aim_valid: bool, connected: bool, now: float | None = None) -> dict:
        now = float(now if now is not None else time.time())
        target_valid = bool(target.get("target_valid", False))
        hold = bool(target.get("target_hold", False))
        preempted = bool(target.get("target_preempted", False))
        track_id = target.get("target_track_id", target.get("track_id"))

        if not connected:
            self.current_track_id = None
            self._set("FAULT", now)
            return {
                "control_state": self.state,
                "beep": 0,
                "light": 0,
                "allow_alarm": False,
                "state_age": round(now - self.state_since, 3),
            }

        if not target_valid or not aim_valid:
            if self.state not in ("IDLE", "RECOVERING"):
                self._set("RECOVERING", now)
            elif self.state == "RECOVERING" and now - self.state_since >= self.recover_seconds:
                self._set("IDLE", now)
                self.current_track_id = None
            return {
                "control_state": self.state,
                "beep": 0,
                "light": 0,
                "allow_alarm": False,
                "state_age": round(now - self.state_since, 3),
            }

        target_changed = self.current_track_id is not None and track_id != self.current_track_id
        if preempted or target_changed:
            self.current_track_id = track_id
            self._set("PREEMPTING", now)
        elif self.current_track_id is None:
            self.current_track_id = track_id
            self._set("AIMING", now)
        elif hold:
            self._set("HOLDING", now)
        elif self.state in ("IDLE", "RECOVERING", "FAULT"):
            self._set("AIMING", now)

        if self.state == "PREEMPTING" and now - self.state_since >= self.aiming_seconds:
            self._set("ALARMING", now)
        elif self.state == "AIMING" and now - self.state_since >= self.aiming_seconds:
            self._set("ALARMING", now)
        elif self.state == "HOLDING" and not hold:
            self._set("ALARMING", now)

        allow_alarm = self.state == "ALARMING" and not hold
        beep = self.alarm_to_beep(target.get("alarm_level", "none")) if allow_alarm else 0
        return {
            "control_state": self.state,
            "beep": int(beep),
            "light": 1 if beep > 0 else 0,
            "allow_alarm": bool(allow_alarm),
            "state_age": round(now - self.state_since, 3),
        }
