from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import yaml

from error_diagnoser import diagnose_file, diagnose_text
from path_utils import safe_copy, windows_to_wsl_path
from utils import append_log, run_command


def _container_task_path(path: str | Path) -> str:
    win_path = str(path).replace("\\", "/")
    marker = "/RDK_ModelPilot_Output/"
    if marker in win_path:
        return "/workspace/task/" + win_path.split(marker, 1)[1].split("/", 1)[-1]
    return "/workspace/task/" + Path(path).name


def write_quant_config(
    onnx_path: str | Path,
    calibration_dir: str | Path,
    task_dir: str | Path,
    config: dict[str, Any],
    input_name: str = "images",
) -> Path:
    task = Path(task_dir)
    model_name = Path(onnx_path).stem
    output_prefix = f"/workspace/task/bin/{model_name}_bayese_{config.get('default_imgsz', 640)}x{config.get('default_imgsz', 640)}_nv12"
    data = {
        "model_parameters": {
            "onnx_model": f"/workspace/task/onnx/{Path(onnx_path).name}",
            "march": "bayes-e",
            "output_model_file_prefix": output_prefix,
            "working_dir": "/workspace/task/bin",
        },
        "input_parameters": {
            "input_name": input_name,
            "input_type_rt": "nv12",
            "input_layout_rt": "NHWC",
            "input_type_train": "rgb",
            "input_layout_train": "NCHW",
            "input_shape": f"1x3x{config.get('default_imgsz', 640)}x{config.get('default_imgsz', 640)}",
            "norm_type": "data_scale",
            "scale_value": 0.003921568627451,
        },
        "calibration_parameters": {
            "cal_data_dir": "/workspace/task/calibration/selected_images",
            "calibration_type": "default",
            "max_percentile": 0.99999,
        },
        "compiler_parameters": {
            "compile_mode": "latency",
            "debug": False,
            "optimize_level": "O3",
        },
    }
    target = task / "configs" / "quant_config.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target


def _mapper_option(help_text: str, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in help_text:
            return candidate
    return None


def _build_mapper_command(help_text: str, task: Path, onnx_path: Path, config: dict[str, Any]) -> str | None:
    model_arg = _mapper_option(help_text, ["--onnx", "--model", "--model-path", "--model_path"])
    calib_arg = _mapper_option(help_text, ["--calibration", "--calib", "--cal-data-dir", "--cal_data_dir", "--calibration-dir"])
    output_arg = _mapper_option(help_text, ["--output", "--output-dir", "--output_dir", "--save-dir"])
    imgsz_arg = _mapper_option(help_text, ["--imgsz", "--input-size", "--input_size"])
    march_arg = _mapper_option(help_text, ["--march", "--target"])
    if not (model_arg and calib_arg and output_arg):
        return None
    parts = [
        "python3",
        "/workspace/rdk_model_zoo/samples/vision/ultralytics_yolo/x86/mapper.py",
        model_arg,
        f"/workspace/task/onnx/{onnx_path.name}",
        calib_arg,
        "/workspace/task/calibration/selected_images",
        output_arg,
        "/workspace/task/bin",
    ]
    if imgsz_arg:
        parts.extend([imgsz_arg, str(config.get("default_imgsz", 640))])
    if march_arg:
        parts.extend([march_arg, "bayes-e"])
    return " ".join(shlex.quote(part) for part in parts)


def _find_bin(task: Path) -> Path | None:
    bins = sorted(task.rglob("*.bin"), key=lambda item: item.stat().st_mtime, reverse=True)
    return bins[0] if bins else None


def build_int8_bin(
    onnx_path: str | Path,
    calibration_dir: str | Path,
    task_dir: str | Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    task = Path(task_dir)
    onnx_file = Path(onnx_path)
    log_path = task / "logs" / "mapper_logs.txt"
    checker_log = task / "logs" / "checker.log"
    makertbin_log = task / "logs" / "makertbin.log"
    append_log(log_path, "Starting OpenExplorer quantization build")

    if not onnx_file.exists():
        message = f"ONNX 文件不存在：{onnx_file}"
        append_log(log_path, message)
        return {"ok": False, "error": message, "diagnosis": diagnose_text(message), "log_path": str(log_path)}
    if not Path(calibration_dir).exists() or not any(Path(calibration_dir).rglob("*")):
        message = f"校准图片为空：{calibration_dir}"
        append_log(log_path, message)
        return {"ok": False, "error": message, "diagnosis": diagnose_text(message), "log_path": str(log_path)}

    quant_config = write_quant_config(onnx_file, calibration_dir, task, config)
    task_wsl = windows_to_wsl_path(task)
    rdk_wsl = config["rdk_model_zoo_wsl"]
    image = config["docker_image"]
    mapper_help_cmd = (
        "python3 /workspace/rdk_model_zoo/samples/vision/ultralytics_yolo/x86/mapper.py --help "
        "> /workspace/task/logs/mapper_help.txt 2>&1 || true"
    )
    help_fetch = (
        f"docker run --rm -v {shlex.quote(task_wsl)}:/workspace/task "
        f"-v {shlex.quote(rdk_wsl)}:/workspace/rdk_model_zoo:ro "
        f"{shlex.quote(image)} bash -lc {shlex.quote(mapper_help_cmd)}"
    )
    run_command(["wsl", "-d", config["wsl_distro"], "bash", "-lc", help_fetch], log_path, timeout=300)
    help_text = (task / "logs" / "mapper_help.txt").read_text(encoding="utf-8", errors="ignore") if (task / "logs" / "mapper_help.txt").exists() else ""
    mapper_command = _build_mapper_command(help_text, task, onnx_file, config)

    if mapper_command:
        inner = (
            f"{mapper_command} > /workspace/task/logs/makertbin.log 2>&1; "
            "cp /workspace/task/logs/makertbin.log /workspace/task/logs/checker.log || true"
        )
    else:
        append_log(log_path, "mapper.py 参数无法可靠推断，使用 hb_mapper checker/makertbin 标准封装。")
        inner = (
            f"hb_mapper checker --model-type onnx --march bayes-e --proto /workspace/task/onnx/{shlex.quote(onnx_file.name)} "
            "> /workspace/task/logs/checker.log 2>&1 && "
            "hb_mapper makertbin --config /workspace/task/configs/quant_config.yaml --model-type onnx "
            "> /workspace/task/logs/makertbin.log 2>&1"
        )

    docker_command = (
        f"docker run --rm -v {shlex.quote(task_wsl)}:/workspace/task "
        f"-v {shlex.quote(rdk_wsl)}:/workspace/rdk_model_zoo:ro "
        f"{shlex.quote(image)} bash -lc {shlex.quote(inner)}"
    )
    result = run_command(["wsl", "-d", config["wsl_distro"], "bash", "-lc", docker_command], log_path, timeout=7200)

    bin_file = _find_bin(task)
    target_bin = task / "bin" / f"{onnx_file.stem}_bayese_{config.get('default_imgsz', 640)}x{config.get('default_imgsz', 640)}_nv12.bin"
    if result.ok and bin_file:
        safe_copy(bin_file, target_bin)
        return {
            "ok": True,
            "bin_path": str(target_bin),
            "quant_config_path": str(quant_config),
            "checker_log": str(checker_log),
            "makertbin_log": str(makertbin_log),
            "mapper_log": str(log_path),
            "used_mapper_py": bool(mapper_command),
            "command": result.command,
            "diagnosis": [],
        }

    diagnosis = diagnose_file(log_path) + diagnose_file(checker_log) + diagnose_file(makertbin_log)
    return {
        "ok": False,
        "error": "OpenExplorer 量化编译失败或未生成 .bin",
        "quant_config_path": str(quant_config),
        "checker_log": str(checker_log),
        "makertbin_log": str(makertbin_log),
        "mapper_log": str(log_path),
        "used_mapper_py": bool(mapper_command),
        "command": result.command,
        "result": result.to_dict(),
        "diagnosis": diagnosis,
    }
