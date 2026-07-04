#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""不依赖 RDK BPU/摄像头的核心逻辑自检。"""

import time
from tracking_manager import TrackManager
from risk_engine import RiskEngine
from target_arbiter import TargetArbiter
from servo_mapper import pixel_to_servo


def main():
    tracker = TrackManager()
    risk = RiskEngine(min_track_hits=2)
    arbiter = TargetArbiter()
    zones = [
        {"id": 1, "name": "高风险区", "zone": [300, 40, 520, 350], "risk_level": "high", "enabled": True, "require_helmet": True, "require_vest": True},
        {"id": 2, "name": "中风险区", "zone": [50, 100, 280, 350], "risk_level": "medium", "enabled": True, "require_helmet": True, "require_vest": False},
    ]
    now = time.time()
    last_target = None
    for i in range(8):
        observations = [
            {"bbox": (360 + i, 80, 440 + i, 310), "score": 0.92, "class_id": 0, "has_helmet": False, "has_vest": True},
            {"bbox": (120, 120, 210, 320), "score": 0.88, "class_id": 0, "has_helmet": False, "has_vest": True},
        ]
        tracks = tracker.update(observations, now=now + i * 0.08)
        evaluated, candidates = risk.evaluate(tracks, zones, now=now + i * 0.08)
        target = arbiter.select(candidates, now=now + i * 0.08)
        if target.get("target_valid"):
            aim = pixel_to_servo(target["target_x"], target["target_y"], target["target_zone_id"])
            assert aim["valid"]
            last_target = target
    assert last_target is not None
    assert last_target["target_zone_id"] == 1
    assert last_target["risk_score"] > 0.6
    print("SELF_TEST_OK", {
        "track_id": last_target["target_track_id"],
        "zone_id": last_target["target_zone_id"],
        "risk_score": round(last_target["risk_score"], 3),
        "switch_count": last_target.get("target_switch_count", 0),
    })


if __name__ == "__main__":
    main()
