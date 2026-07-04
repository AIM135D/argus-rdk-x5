from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "online"))

from control_state_machine import ControlStateMachine
from risk_engine import RiskEngine
from target_arbiter import TargetArbiter


class RiskEngineTests(unittest.TestCase):
    def test_ppe_violation_becomes_ready_candidate(self):
        engine = RiskEngine(min_track_hits=2)
        tracks = [
            {
                "track_id": 7,
                "score": 0.95,
                "smoothed_center": (400.0, 190.0),
                "smoothed_foot": (400.0, 320.0),
                "velocity_x": 12.0,
                "velocity_y": 0.0,
                "helmet_prob": 0.0,
                "vest_prob": 1.0,
                "has_helmet_stable": False,
                "has_vest_stable": True,
                "track_age_frames": 8,
                "track_hits": 8,
            }
        ]
        zones = [
            {
                "id": 1,
                "name": "机械作业区",
                "zone": [300, 40, 520, 350],
                "risk_level": "high",
                "enabled": True,
                "require_helmet": True,
                "require_vest": True,
            }
        ]

        engine.evaluate(tracks, zones, now=100.0)
        evaluated, candidates = engine.evaluate(tracks, zones, now=103.0)

        self.assertTrue(evaluated[0]["is_danger"])
        self.assertEqual(candidates[0]["target_zone_id"], 1)
        self.assertTrue(candidates[0]["missing_helmet"])
        self.assertFalse(candidates[0]["missing_vest"])
        self.assertTrue(candidates[0]["candidate_ready"])
        self.assertGreater(candidates[0]["risk_score"], 0.6)


class TargetArbiterTests(unittest.TestCase):
    @staticmethod
    def candidate(track_id, risk_score, x):
        return {
            "track_id": track_id,
            "target_valid": True,
            "candidate_ready": True,
            "target_x": x,
            "target_y": 180,
            "target_conf": 0.9,
            "target_zone_id": 1,
            "target_zone_name": "zone",
            "target_reason": "missing_helmet",
            "target_point_type": "smoothed_foot",
            "risk_score": risk_score,
            "alarm_level": "high",
            "danger_duration": 1.0,
        }

    def test_hysteresis_then_high_risk_preemption(self):
        arbiter = TargetArbiter(preempt_margin=0.06)
        first = arbiter.select([self.candidate(1, 0.60, 200)], now=10.0)
        held = arbiter.select(
            [self.candidate(1, 0.60, 200), self.candidate(2, 0.62, 440)],
            now=10.1,
        )
        switched = arbiter.select(
            [self.candidate(1, 0.50, 200), self.candidate(2, 0.92, 440)],
            now=10.2,
        )

        self.assertEqual(first["target_track_id"], 1)
        self.assertEqual(held["target_track_id"], 1)
        self.assertEqual(switched["target_track_id"], 2)
        self.assertTrue(switched["target_preempted"])


class ControlStateMachineTests(unittest.TestCase):
    def test_aim_alarm_hold_and_recover(self):
        machine = ControlStateMachine(
            aiming_seconds=0.2, recover_seconds=0.1
        )
        target = {
            "target_valid": True,
            "target_track_id": 3,
            "target_hold": False,
            "target_preempted": False,
            "alarm_level": "high",
        }

        aiming = machine.update(target, True, True, now=10.0)
        alarming = machine.update(target, True, True, now=10.3)
        holding = machine.update(
            {**target, "target_hold": True}, True, True, now=10.4
        )
        recovering = machine.update({}, False, True, now=10.5)
        idle = machine.update({}, False, True, now=10.7)

        self.assertEqual(aiming["control_state"], "AIMING")
        self.assertEqual(alarming["control_state"], "ALARMING")
        self.assertEqual(alarming["beep"], 3)
        self.assertEqual(holding["control_state"], "HOLDING")
        self.assertEqual(holding["beep"], 0)
        self.assertEqual(recovering["control_state"], "RECOVERING")
        self.assertEqual(idle["control_state"], "IDLE")


if __name__ == "__main__":
    unittest.main()
