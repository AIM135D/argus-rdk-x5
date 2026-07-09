from __future__ import annotations

import os
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from calibration_checker import check_calibration_set
from config_manager import init_config, load_config, save_config, update_related_paths, validate_paths
from deploy_config_generator import generate_deploy_config
from env_checker import check_environment
from error_diagnoser import diagnose_text
from installer import install_environment
from model_exporter import export_onnx_model
from onnx_checker import check_onnx_structure
from path_utils import ensure_dir, safe_copy
from quant_builder import build_int8_bin
from report_generator import generate_deploy_report
from utils import LOG_DIR, append_log, copy_inputs_to_task, create_task_dir, file_info, parse_data_yaml, read_text_tail, write_json


app = FastAPI(title="RDK ModelPilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "file://"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_config()

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


class ConfigPayload(BaseModel):
    config: dict[str, Any]


class ModelInspectRequest(BaseModel):
    pt_path: str = ""
    data_yaml_path: str = ""
    calibration_dir: str = ""
    output_dir: str = ""
    manual_classes: list[str] = Field(default_factory=list)


class CalibrationRequest(BaseModel):
    calibration_dir: str
    task_dir: str = ""


class ConvertRequest(BaseModel):
    pt_path: str
    data_yaml_path: str = ""
    calibration_dir: str
    output_dir: str = ""
    manual_classes: list[str] = Field(default_factory=list)
    imgsz: int | None = None
    use_wsl_export: bool = False


class OpenPathRequest(BaseModel):
    path: str


def _job_runner(job_id: str, func: Any, *args: Any, **kwargs: Any) -> None:
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "running"
    try:
        result = func(*args, **kwargs)
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "success" if result.get("ok", True) else "failed"
            JOBS[job_id]["result"] = result
    except Exception as exc:  # noqa: BLE001 - jobs must surface all exceptions to UI.
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["result"] = {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "diagnosis": diagnose_text(str(exc)),
            }


def start_job(name: str, func: Any, *args: Any, inject_job_id: bool = False, **kwargs: Any) -> dict[str, str]:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"id": job_id, "name": name, "status": "queued", "result": None}
    if inject_job_id:
        kwargs["_job_id"] = job_id
    thread = threading.Thread(target=_job_runner, args=(job_id, func, *args), kwargs=kwargs, daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "queued"}


def _step_names() -> list[str]:
    return [
        "[1/8] 准备任务目录",
        "[2/8] 校准集质量检查",
        "[3/8] 导出 ONNX",
        "[4/8] 检查 ONNX 结构",
        "[5/8] hb_mapper checker",
        "[6/8] INT8 量化编译 makertbin",
        "[7/8] 生成 deploy_config.py",
        "[8/8] 生成 deploy_report.md",
    ]


def _init_status(task_dir: Path) -> dict[str, Any]:
    state = {
        "task_dir": str(task_dir),
        "steps": [{"name": name, "status": "waiting", "message": ""} for name in _step_names()],
        "result": {},
    }
    write_json(task_dir / "status.json", state)
    return state


def _set_step(task_dir: Path, state: dict[str, Any], index: int, step_status: str, message: str = "") -> None:
    state["steps"][index]["status"] = step_status
    state["steps"][index]["message"] = message
    write_json(task_dir / "status.json", state)
    append_log(task_dir / "logs" / "app.log", f"{state['steps'][index]['name']} {step_status} {message}")


def run_conversion_pipeline(request: ConvertRequest, _job_id: str | None = None) -> dict[str, Any]:
    cfg = load_config()
    if request.imgsz:
        cfg["default_imgsz"] = request.imgsz
    output_dir = request.output_dir or cfg["output_dir"]
    ensure_dir(output_dir)
    task_dir = create_task_dir(output_dir, request.pt_path)
    state = _init_status(task_dir)
    if _job_id:
        with JOBS_LOCK:
            if _job_id in JOBS:
                JOBS[_job_id]["result"] = {
                    "ok": None,
                    "task_dir": str(task_dir),
                    "status_path": str(task_dir / "status.json"),
                    "app_log": str(task_dir / "logs" / "app.log"),
                }

    _set_step(task_dir, state, 0, "running")
    copied = copy_inputs_to_task(task_dir, request.pt_path, request.data_yaml_path or None)
    pt_in_task = copied["pt"]
    data_yaml_in_task = copied.get("data_yaml", request.data_yaml_path)
    data_yaml = parse_data_yaml(data_yaml_in_task, request.manual_classes or None)
    class_validation = data_yaml.get("validation", {})
    if not class_validation.get("ok", False):
        message = "; ".join(class_validation.get("errors", [])) or "类别配置不合法。"
        _set_step(task_dir, state, 0, "failed", message)
        state["result"]["data_yaml"] = data_yaml
        write_json(task_dir / "status.json", state)
        return {
            "ok": False,
            "task_dir": str(task_dir),
            "status_path": str(task_dir / "status.json"),
            "data_yaml": data_yaml,
            "error": message,
            "diagnosis": diagnose_text(message),
        }
    env_report = LOG_DIR / "env_check_report.md"
    if env_report.exists():
        safe_copy(env_report, task_dir / "reports" / "env_check_report.md")
    _set_step(task_dir, state, 0, "success", str(task_dir))

    _set_step(task_dir, state, 1, "running", request.calibration_dir)
    calibration = check_calibration_set(request.calibration_dir, task_dir)
    if calibration["summary"]["errors"]:
        _set_step(task_dir, state, 1, "failed", "; ".join(calibration["summary"]["errors"]))
        state["result"]["calibration"] = calibration
        write_json(task_dir / "status.json", state)
        return {"ok": False, "task_dir": str(task_dir), "status_path": str(task_dir / "status.json"), "calibration": calibration}
    _set_step(task_dir, state, 1, "warning" if calibration["summary"]["warnings"] else "success", "; ".join(calibration["summary"]["warnings"][:2]))

    _set_step(task_dir, state, 2, "running")
    export = export_onnx_model(pt_in_task, task_dir, cfg, cfg.get("default_imgsz", 640), request.use_wsl_export)
    state["result"]["export"] = export
    if not export.get("ok"):
        _set_step(task_dir, state, 2, "failed", export.get("error", "ONNX 导出失败"))
        write_json(task_dir / "status.json", state)
        return {"ok": False, "task_dir": str(task_dir), "status_path": str(task_dir / "status.json"), "export": export}
    _set_step(task_dir, state, 2, "success", export["onnx_path"])

    _set_step(task_dir, state, 3, "running")
    onnx_check = check_onnx_structure(export["onnx_path"], int(data_yaml["nc"]), task_dir, int(cfg.get("default_imgsz", 640)))
    state["result"]["onnx_check"] = onnx_check
    if not onnx_check.get("ok"):
        _set_step(task_dir, state, 3, "failed", onnx_check.get("warning", "ONNX 结构不适配"))
        deploy_config = generate_deploy_config(task_dir, data_yaml["names"], cfg, None, onnx_check)
        report = generate_deploy_report(task_dir, pt_in_task, data_yaml, cfg, onnx_check, {}, calibration, deploy_config["deploy_config_path"])
        state["result"].update({"deploy_config": deploy_config, "report": report})
        write_json(task_dir / "status.json", state)
        return {
            "ok": False,
            "task_dir": str(task_dir),
            "status_path": str(task_dir / "status.json"),
            "onnx_check": onnx_check,
            "deploy_config": deploy_config,
            "report": report,
        }
    _set_step(task_dir, state, 3, "success")

    _set_step(task_dir, state, 4, "running")
    _set_step(task_dir, state, 5, "running")
    quant = build_int8_bin(export["onnx_path"], calibration["selected_dir"], task_dir, cfg)
    state["result"]["quant"] = quant
    if not quant.get("ok"):
        _set_step(task_dir, state, 4, "failed", "checker 或 mapper 失败")
        _set_step(task_dir, state, 5, "failed", quant.get("error", "makertbin 失败"))
        write_json(task_dir / "status.json", state)
        return {
            "ok": False,
            "task_dir": str(task_dir),
            "status_path": str(task_dir / "status.json"),
            "export": export,
            "onnx_check": onnx_check,
            "quant": quant,
        }
    _set_step(task_dir, state, 4, "success", quant.get("checker_log", ""))
    _set_step(task_dir, state, 5, "success", quant.get("bin_path", ""))

    _set_step(task_dir, state, 6, "running")
    deploy_config = generate_deploy_config(task_dir, data_yaml["names"], cfg, quant.get("bin_path"), onnx_check)
    _set_step(task_dir, state, 6, "success", deploy_config["deploy_config_path"])

    _set_step(task_dir, state, 7, "running")
    report = generate_deploy_report(task_dir, pt_in_task, data_yaml, cfg, onnx_check, quant, calibration, deploy_config["deploy_config_path"])
    _set_step(task_dir, state, 7, "success", report["deploy_report_path"])

    result = {
        "ok": True,
        "task_dir": str(task_dir),
        "status_path": str(task_dir / "status.json"),
        "onnx_path": export["onnx_path"],
        "bin_path": quant.get("bin_path", ""),
        "deploy_config_path": deploy_config["deploy_config_path"],
        "deploy_report_path": report["deploy_report_path"],
        "env_check_report_path": str(task_dir / "reports" / "env_check_report.md"),
        "calibration_report_path": calibration["report_path"],
        "onnx_structure_report_path": onnx_check["report_path"],
        "logs": {
            "app": str(task_dir / "logs" / "app.log"),
            "export": export.get("log_path", ""),
            "mapper": quant.get("mapper_log", ""),
            "checker": quant.get("checker_log", ""),
            "makertbin": quant.get("makertbin_log", ""),
        },
    }
    state["result"] = result
    write_json(task_dir / "status.json", state)
    return result


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": "RDK ModelPilot", "version": "0.1.0"}


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    cfg = load_config()
    return {"config": cfg, "paths": validate_paths(cfg)}


@app.post("/api/config")
def update_config(payload: ConfigPayload) -> dict[str, Any]:
    cfg = save_config(update_related_paths(payload.config))
    return {"ok": True, "config": cfg, "paths": validate_paths(cfg)}


@app.get("/api/env/check")
def api_env_check() -> dict[str, Any]:
    return check_environment(load_config())


@app.post("/api/env/install")
def api_env_install() -> dict[str, str]:
    return start_job("env_install", install_environment)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        if job_id not in JOBS:
            raise HTTPException(status_code=404, detail="job not found")
        return JOBS[job_id]


@app.post("/api/model/inspect")
def inspect_model(request: ModelInspectRequest) -> dict[str, Any]:
    cfg = load_config()
    output_dir = request.output_dir or cfg["output_dir"]
    response: dict[str, Any] = {
        "output_dir": output_dir,
        "default_imgsz": cfg["default_imgsz"],
        "target": cfg["target"],
        "runtime_input": cfg["runtime_input"],
    }
    if request.pt_path:
        path = Path(request.pt_path)
        if not path.exists():
            raise HTTPException(status_code=400, detail=f".pt 文件不存在：{path}")
        response["pt"] = file_info(path)
        response["recommended_onnx"] = str(Path(output_dir) / f"{path.stem}_timestamp" / "onnx" / f"{path.stem}.onnx")
        response["recommended_bin"] = str(Path(output_dir) / f"{path.stem}_timestamp" / "bin" / f"{path.stem}_bayese_{cfg['default_imgsz']}x{cfg['default_imgsz']}_nv12.bin")
    if request.data_yaml_path or request.manual_classes:
        response["data_yaml"] = parse_data_yaml(request.data_yaml_path, request.manual_classes or None)
    if request.calibration_dir:
        response["calibration_preview"] = check_calibration_set(request.calibration_dir)
    return response


@app.post("/api/calibration/check")
def api_calibration_check(request: CalibrationRequest) -> dict[str, Any]:
    return check_calibration_set(request.calibration_dir, request.task_dir or None)


@app.post("/api/convert/run")
def api_convert_run(request: ConvertRequest) -> dict[str, str]:
    return start_job("convert", run_conversion_pipeline, request, inject_job_id=True)


@app.get("/api/task/status")
def task_status(path: str = Query(...)) -> dict[str, Any]:
    target = Path(path)
    if target.is_dir():
        target = target / "status.json"
    if not target.exists():
        raise HTTPException(status_code=404, detail="status file not found")
    import json

    return json.loads(target.read_text(encoding="utf-8"))


@app.get("/api/logs/read")
def read_log(path: str = Query(...), max_chars: int = Query(20000, ge=1000, le=200000)) -> dict[str, str]:
    return {"path": path, "content": read_text_tail(path, max_chars=max_chars)}


@app.post("/api/open-path")
def open_path(request: OpenPathRequest) -> dict[str, Any]:
    target = Path(request.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"路径不存在：{target}")
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    else:
        raise HTTPException(status_code=400, detail="当前系统不是 Windows，无法调用 explorer 打开路径。")
    return {"ok": True, "path": str(target)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
