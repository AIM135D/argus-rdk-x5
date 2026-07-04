#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过本机 FastAPI 手动测试协议 A 角度，便于现场标定。"""

import argparse
import json
import urllib.request


BASE = "http://127.0.0.1:8000"


def post(path, payload=None):
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pan", type=int)
    parser.add_argument("--tilt", type=int)
    parser.add_argument("--beep", type=int, default=0)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--show", action="store_true", help="显示当前标定 JSON")
    args = parser.parse_args()

    if args.stop:
        print(json.dumps(post("/api/hardware/manual_stop"), ensure_ascii=False, indent=2))
        return
    if args.show:
        print(json.dumps(get("/api/calibration"), ensure_ascii=False, indent=2))
        return
    if args.pan is None or args.tilt is None:
        parser.error("需要 --pan 和 --tilt，或使用 --show/--stop")
    result = post("/api/hardware/manual_aim", {
        "pan": args.pan,
        "tilt": args.tilt,
        "beep": args.beep,
        "duration": args.duration,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
