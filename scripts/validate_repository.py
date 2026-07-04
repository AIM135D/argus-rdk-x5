#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BLOCKED_SUFFIXES = {
    ".pt",
    ".pth",
    ".onnx",
    ".bin",
    ".engine",
    ".zip",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
}
BLOCKED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    "datasets",
    "calibration_images",
    "screenshots",
}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".sh",
    ".ino",
    ".txt",
}
PERSONAL_PATHS = [
    re.compile(r"/Users/[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\", re.IGNORECASE),
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if ".git" in relative.parts:
            continue
        if any(part in BLOCKED_PARTS for part in relative.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            fail(f"blocked binary/model/media file: {relative}")
        if path.stat().st_size > 50 * 1024 * 1024:
            fail(f"file exceeds 50 MiB: {relative}")
        if (
            path.suffix.lower() in TEXT_SUFFIXES
            and relative != Path("scripts/validate_repository.py")
        ):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in PERSONAL_PATHS:
                if pattern.search(text):
                    fail(f"personal absolute path in {relative}")

    for relative in (
        "configs/danger_zones.example.json",
        "configs/servo_calibration.example.json",
        "models/model_manifest.json",
    ):
        json.loads((ROOT / relative).read_text(encoding="utf-8"))

    for relative in (
        "configs/runtime.example.yaml",
        "configs/model_profiles/ppe_dfl_640_rdkx5.yaml",
        ".github/workflows/ci.yml",
    ):
        yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))

    runtime = yaml.safe_load(
        (ROOT / "configs/runtime.example.yaml").read_text(encoding="utf-8")
    )
    expected = {
        "hardware_enabled": False,
        "servo_enabled": False,
        "buzzer_enabled": False,
        "llm_bridge_enabled": False,
        "host": "127.0.0.1",
        "port": 8000,
    }
    for key, value in expected.items():
        if runtime.get(key) != value:
            fail(f"unsafe runtime default: {key}={runtime.get(key)!r}")

    print("repository validation passed")


if __name__ == "__main__":
    main()
