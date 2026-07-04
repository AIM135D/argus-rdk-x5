# -*- coding: utf-8 -*-
"""ESP32 主动定向声光预警线程（A/T/AT 真兼容版）。

- A:  RDK 计算 pan/tilt，发送 A,seq,zone_id,pan,tilt,score,light,beep
- T:  发送 T,seq,zone_id,cx,cy,img_w,img_h,score,light,beep
- AT: 发送旧 @T 归一化坐标协议

只修改 ESP32_PROTOCOL 即可真正切换协议。
"""

import time

from config import (
    BUZZER_ENABLED,
    ESP32_BAUDRATE,
    ESP32_PORT,
    ESP32_PROTOCOL,
    ESP32_SEND_HZ,
    HARDWARE_ENABLED,
    LIGHT_ENABLED,
    SERVO_ENABLED,
    STREAM_HEIGHT,
    STREAM_WIDTH,
)
from control_state_machine import ControlStateMachine
from esp32_bridge import ESP32Bridge
from servo_mapper import limit_step, pixel_to_servo
from state import state


ESP32_ENABLE = HARDWARE_ENABLED and SERVO_ENABLED
SEND_CENTER_ON_START = True
SEND_LOST_WHEN_NO_TARGET = True
SERVO_MAX_STEP_PER_SEND = 6
SERIAL_RECONNECT_SECONDS = 1.0


def _send_by_protocol(bridge, protocol, target, aim, beep, light):
    protocol = str(protocol or "T").upper()
    zone_id = target.get("target_zone_id", 0)
    score = target.get("risk_score", target.get("target_conf", 0.0))

    if protocol == "A":
        return bridge.send_aim(
            zone_id=zone_id,
            pan=aim.get("pan", 90),
            tilt=aim.get("tilt", 90),
            score=score,
            beep=beep,
            light=light,
        )

    # T / AT 发送图像坐标，由 ESP32 旧固件自行换算角度。
    return bridge.send_target(
        zone_id=zone_id,
        cx=target.get("target_x", -1),
        cy=target.get("target_y", -1),
        img_w=STREAM_WIDTH,
        img_h=STREAM_HEIGHT,
        score=score,
        beep=beep,
        light=light,
    )


def hardware_loop():
    if not ESP32_ENABLE:
        print("ℹ️ ESP32_ENABLE=False，主动定向预警线程未启用")
        return

    protocol = str(ESP32_PROTOCOL or "T").upper()
    bridge = ESP32Bridge(
        port=ESP32_PORT,
        baudrate=ESP32_BAUDRATE,
        protocol=protocol,
    )
    controller = ControlStateMachine(aiming_seconds=0.30, recover_seconds=0.45)
    period = 1.0 / max(1.0, float(ESP32_SEND_HZ))

    centered = False
    last_sent_pan = None
    last_sent_tilt = None
    last_lost_send = 0.0

    print(f"✅ ESP32 主动定向预警线程启动: port={ESP32_PORT}, protocol={protocol}")

    while state.running:
        now = time.time()

        if not bridge.connect():
            control = controller.update({}, False, False, now)
            with state.lock:
                state.latest_info.update({
                    "esp32_connected": False,
                    "esp32_port": ESP32_PORT,
                    "esp32_protocol": protocol,
                    "esp32_last_error": bridge.last_error,
                    "servo_aim_valid": False,
                    "buzzer_level": 0,
                    "buzzer_active": False,
                    "control_state": control["control_state"],
                    "control_state_age": control["state_age"],
                })
            time.sleep(SERIAL_RECONNECT_SECONDS)
            continue

        if not centered and SEND_CENTER_ON_START:
            bridge.send_center()
            centered = True
            last_sent_pan, last_sent_tilt = 90, 90
            time.sleep(0.20)

        with state.lock:
            target = dict(state.latest_info)

        manual_active = (
            bool(target.get("manual_aim_active", False))
            and now <= float(target.get("manual_aim_until", 0.0) or 0.0)
        )
        if bool(target.get("manual_aim_active", False)) and not manual_active:
            with state.lock:
                state.latest_info["manual_aim_active"] = False

        target_valid = bool(target.get("target_valid", False))
        aim = {
            "valid": False,
            "pan": 90,
            "tilt": 90,
            "mode": "none",
            "map_name": "-",
        }

        if manual_active and protocol == "A":
            target_valid = True
            target = dict(target)
            target.update({
                "target_valid": True,
                "target_zone_id": 0,
                "target_track_id": None,
                "target_hold": False,
                "target_preempted": False,
                "alarm_level": (
                    "high"
                    if int(target.get("manual_aim_beep", 0) or 0) >= 3
                    else "medium"
                ),
                "risk_score": 1.0,
            })
            aim = {
                "valid": True,
                "pan": int(target.get("manual_aim_pan", 90)),
                "tilt": int(target.get("manual_aim_tilt", 90)),
                "mode": "manual",
                "map_name": "manual_test",
            }
        elif target_valid:
            aim = pixel_to_servo(
                cx=target.get("target_x", -1),
                cy=target.get("target_y", -1),
                zone_id=target.get("target_zone_id"),
            )

        if aim.get("valid") and protocol == "A":
            if last_sent_pan is not None and last_sent_tilt is not None:
                aim["pan"] = limit_step(
                    last_sent_pan, aim["pan"], SERVO_MAX_STEP_PER_SEND
                )
                aim["tilt"] = limit_step(
                    last_sent_tilt, aim["tilt"], SERVO_MAX_STEP_PER_SEND
                )

        # T/AT 不依赖标定角度，只要目标坐标有效就允许发送。
        execution_valid = target_valid and (
            bool(aim.get("valid")) if protocol == "A" else True
        )

        control = controller.update(target, execution_valid, True, now)
        if manual_active and protocol == "A":
            manual_beep = max(0, min(3, int(target.get("manual_aim_beep", 0) or 0)))
            control = {
                "control_state": "MANUAL",
                "beep": manual_beep,
                "light": 1 if manual_beep > 0 else 0,
                "allow_alarm": True,
                "state_age": 0.0,
            }

        beep = int(control["beep"]) if BUZZER_ENABLED else 0
        light = int(bool(control["light"]) and LIGHT_ENABLED)
        ok = True

        if execution_valid:
            ok = _send_by_protocol(
                bridge, protocol, target, aim, beep, light
            )
            if ok and protocol == "A":
                last_sent_pan, last_sent_tilt = aim["pan"], aim["tilt"]
        elif SEND_LOST_WHEN_NO_TARGET and now - last_lost_send >= 0.45:
            ok = bridge.send_lost()
            last_lost_send = now

        snap = bridge.snapshot()
        with state.lock:
            state.latest_info.update({
                "esp32_connected": bool(snap["connected"]),
                "esp32_port": snap["port"],
                "esp32_protocol": protocol,
                "esp32_last_cmd": snap["last_cmd"],
                "esp32_last_ack": snap["last_ack"],
                "esp32_last_error": snap["last_error"],
                "esp32_seq": snap["seq"],
                "servo_aim_valid": bool(execution_valid),
                "servo_pan": aim.get("pan") if aim.get("valid") else None,
                "servo_tilt": aim.get("tilt") if aim.get("valid") else None,
                "servo_map_mode": aim.get("mode", "none"),
                "servo_map_name": aim.get("map_name", "-"),
                "servo_hold_mode": bool(target.get("target_hold", False)),
                "buzzer_level": beep,
                "buzzer_active": bool(beep > 0),
                "control_state": control["control_state"],
                "control_state_age": control["state_age"],
                "control_allow_alarm": control["allow_alarm"],
            })

        time.sleep(0.5 if not ok else period)

    try:
        bridge.send_lost()
        bridge.close()
    except Exception:
        pass
