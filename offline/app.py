# app.py
# -*- coding: utf-8 -*-

import asyncio
import copy
import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from capture import capture_loop
from config import HARDWARE_ENABLED, HOST, PORT
from detector import inference_loop
from monitor import monitor_loop
from servo_mapper import get_calibration, reload_calibration, save_calibration
from hardware_loop import hardware_loop
from state import (
    add_event_log,
    set_current_danger_zone,
    set_current_danger_zones,
    state,
)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    capture_worker = threading.Thread(target=capture_loop, daemon=True)
    infer_worker = threading.Thread(target=inference_loop, daemon=True)
    monitor_worker = threading.Thread(target=monitor_loop, daemon=True)
    capture_worker.start()
    infer_worker.start()
    monitor_worker.start()
    if HARDWARE_ENABLED:
        hardware_worker = threading.Thread(target=hardware_loop, daemon=True)
        hardware_worker.start()

    print("✅ 采集线程已启动")
    print("✅ 推理线程已启动")
    print("✅ 性能监控线程已启动")
    print(
        "✅ ESP32 舵机/蜂鸣器线程已启动"
        if HARDWARE_ENABLED
        else "ℹ️ 硬件输出默认关闭；设置 hardware_enabled=true 后启用"
    )

    yield

    state.running = False
    print("程序正在退出...")


app = FastAPI(
    title="RDK X5 实时危险区域监控",
    lifespan=lifespan
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "web" / "static")),
    name="static",
)


@app.get("/")
async def index():
    try:
        with (BASE_DIR / "web" / "index.html").open("r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except Exception as e:
        return HTMLResponse(
            f"<h2>index.html 加载失败</h2><pre>{str(e)}</pre>",
            status_code=500
        )


@app.get("/api/status")
async def api_status():
    with state.lock:
        payload = dict(state.latest_info)
        payload["danger_zones"] = copy.deepcopy(state.danger_zones)
        payload["danger_zone"] = state.danger_zones[0]["zone"][:] if state.danger_zones else []
        return JSONResponse(payload)


@app.get("/api/logs")
async def api_logs():
    with state.lock:
        return JSONResponse(state.event_logs)


# 旧接口：单危险区（兼容旧前端和旧逻辑）
@app.get("/api/danger_zone")
async def api_get_danger_zone():
    with state.lock:
        zone = state.danger_zones[0]["zone"][:] if state.danger_zones else []
        return JSONResponse({"danger_zone": zone})


@app.post("/api/danger_zone")
async def api_set_danger_zone(data: dict = Body(...)):
    zone = data.get("danger_zone")
    if not isinstance(zone, list) or len(zone) != 4:
        return JSONResponse(
            {"ok": False, "msg": "danger_zone 参数错误"},
            status_code=400
        )

    ok, normalized_zone = set_current_danger_zone(zone)
    if not ok:
        return JSONResponse(
            {"ok": False, "msg": "保存失败"},
            status_code=500
        )

    add_event_log(
        "zone_update",
        f"{time.strftime('%H:%M:%S')} 第一个危险区域已更新为 {normalized_zone}"
    )

    return JSONResponse({"ok": True, "danger_zone": normalized_zone})


# 新接口：多危险区
@app.get("/api/danger_zones")
async def api_get_danger_zones():
    with state.lock:
        return JSONResponse({"danger_zones": copy.deepcopy(state.danger_zones)})


@app.post("/api/danger_zones")
async def api_set_danger_zones(data: dict = Body(...)):
    zones = data.get("danger_zones")

    if not isinstance(zones, list) or len(zones) == 0:
        return JSONResponse(
            {"ok": False, "msg": "danger_zones 参数错误"},
            status_code=400
        )

    ok, normalized_zones = set_current_danger_zones(zones)
    if not ok:
        return JSONResponse(
            {"ok": False, "msg": "保存失败"},
            status_code=500
        )

    add_event_log(
        "zones_update",
        f"{time.strftime('%H:%M:%S')} 危险区域列表已更新，共 {len(normalized_zones)} 个区域",
        extra={"danger_zones": normalized_zones}
    )

    first_zone = normalized_zones[0]["zone"][:] if normalized_zones else []

    return JSONResponse({
        "ok": True,
        "danger_zones": normalized_zones,
        "danger_zone": first_zone,
    })


@app.get("/api/calibration")
async def api_get_calibration():
    return JSONResponse(get_calibration())


@app.post("/api/calibration")
async def api_save_calibration(data: dict = Body(...)):
    try:
        saved = save_calibration(data)
        add_event_log("calibration_update", f"{time.strftime('%H:%M:%S')} 舵机稀疏标定配置已更新")
        return JSONResponse({"ok": True, "calibration": saved})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=400)


@app.post("/api/calibration/reload")
async def api_reload_calibration():
    try:
        return JSONResponse({"ok": True, "calibration": reload_calibration()})
    except Exception as e:
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@app.post("/api/hardware/manual_aim")
async def api_manual_aim(data: dict = Body(...)):
    try:
        pan = max(0, min(180, int(round(float(data.get("pan", 90))))))
        tilt = max(0, min(180, int(round(float(data.get("tilt", 90))))))
        beep = max(0, min(3, int(data.get("beep", 0))))
        duration = max(0.2, min(30.0, float(data.get("duration", 5.0))))
    except Exception:
        return JSONResponse({"ok": False, "msg": "pan/tilt/beep/duration 参数错误"}, status_code=400)

    with state.lock:
        state.latest_info["manual_aim_active"] = True
        state.latest_info["manual_aim_pan"] = pan
        state.latest_info["manual_aim_tilt"] = tilt
        state.latest_info["manual_aim_beep"] = beep
        state.latest_info["manual_aim_until"] = time.time() + duration

    return JSONResponse({
        "ok": True,
        "pan": pan,
        "tilt": tilt,
        "beep": beep,
        "duration": duration,
        "protocol": "A",
    })


@app.post("/api/hardware/manual_stop")
async def api_manual_stop():
    with state.lock:
        state.latest_info["manual_aim_active"] = False
        state.latest_info["manual_aim_beep"] = 0
        state.latest_info["manual_aim_until"] = 0.0
    return JSONResponse({"ok": True})


@app.websocket("/ws_frame")
async def ws_frame(websocket: WebSocket):
    await websocket.accept()

    with state.lock:
        state.clients.append(websocket)
        state.latest_info["online"] = len(state.clients)

    try:
        last_frame_id = -1

        while True:
            with state.lock:
                frame_bytes = state.latest_jpeg
                frame_id = state.latest_info["frame_id"]

            if frame_bytes is not None and frame_id != last_frame_id:
                await websocket.send_bytes(frame_bytes)
                last_frame_id = frame_id
            else:
                await asyncio.sleep(0.001)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("ws_frame error:", e)
    finally:
        with state.lock:
            if websocket in state.clients:
                state.clients.remove(websocket)
            state.latest_info["online"] = len(state.clients)


@app.websocket("/ws_meta")
async def ws_meta(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            with state.lock:
                payload = dict(state.latest_info)
                payload["danger_zones"] = copy.deepcopy(state.danger_zones)
                payload["danger_zone"] = state.danger_zones[0]["zone"][:] if state.danger_zones else []

            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
            await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("ws_meta error:", e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=False)
