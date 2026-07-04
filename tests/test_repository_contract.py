from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_required_public_files_exist(self):
        required = [
            "README.md",
            "README_CN.md",
            "LICENSE",
            "requirements.txt",
            "online/app.py",
            "offline/app.py",
            "firmware/esp32/active_warning_controller/active_warning_controller.ino",
            "models/README.md",
            "models/MODEL_CARD.md",
            "models/model_manifest.json",
            "docs/DEPLOYMENT_RDK_X5.md",
            "docs/HARDWARE_AND_WIRING.md",
            "docs/SERIAL_PROTOCOL.md",
            "docs/MODEL_PIPELINE.md",
            "docs/CALIBRATION.md",
            "docs/SAFETY_AND_LIMITATIONS.md",
        ]
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual(missing, [])

    def test_safe_runtime_defaults(self):
        data = yaml.safe_load(
            (ROOT / "configs/runtime.example.yaml").read_text(
                encoding="utf-8"
            )
        )
        for key in (
            "hardware_enabled",
            "servo_enabled",
            "buzzer_enabled",
            "llm_bridge_enabled",
        ):
            self.assertIs(data[key], False)
        self.assertEqual(data["host"], "127.0.0.1")
        self.assertEqual(data["port"], 8000)

    def test_model_manifest_contract(self):
        data = json.loads(
            (ROOT / "models/model_manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(data["release_policy"]["publish_models"])
        self.assertEqual(
            data["interface"]["classes"],
            ["person", "helmet", "reflective_vest"],
        )
        self.assertEqual(data["interface"]["strides"], [8, 16, 32])
        self.assertEqual(data["interface"]["reg_max"], 16)
        self.assertEqual(data["interface"]["output_count"], 6)
        self.assertTrue(all(not item["published"] for item in data["artifacts"]))


if __name__ == "__main__":
    unittest.main()
