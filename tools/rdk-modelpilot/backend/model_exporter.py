from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from error_diagnoser import diagnose_file, diagnose_text
from path_utils import safe_copy, windows_to_wsl_path
from utils import append_log, run_command


def _find_exported_onnx(search_roots: list[Path], model_stem: str, started_at: float) -> Path | None:
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.onnx"):
            try:
                if path.stat().st_mtime + 2 >= started_at:
                    candidates.append(path)
            except OSError:
                continue
    if not candidates:
        for root in search_roots:
            candidate = root / f"{model_stem}.onnx"
            if candidate.exists():
                candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.stem == model_stem, item.stat().st_mtime), reverse=True)
    return candidates[0]


def export_onnx_model(
    pt_path: str | Path,
    task_dir: str | Path,
    config: dict[str, Any],
    imgsz: int | None = None,
    use_wsl: bool = False,
) -> dict[str, Any]:
    task = Path(task_dir)
    log_path = task / "logs" / "export_onnx.log"
    pt = Path(pt_path)
    export_script = Path(config["export_script_windows"])
    imgsz = int(imgsz or config.get("default_imgsz", 640))
    append_log(log_path, f"Starting ONNX export for {pt}")

    if not pt.exists():
        message = f"模型文件不存在：{pt}"
        append_log(log_path, message)
        return {"ok": False, "error": message, "log_path": str(log_path), "diagnosis": diagnose_text(message)}
    if not export_script.exists() and not use_wsl:
        message = f"export_monkey_patch.py 不存在：{export_script}"
        append_log(log_path, message)
        return {"ok": False, "error": message, "log_path": str(log_path), "diagnosis": diagnose_text(message)}

    started_at = time.time()
    if use_wsl:
        wsl_pt = windows_to_wsl_path(pt)
        command_text = (
            f"source ~/miniconda3/etc/profile.d/conda.sh && conda activate {config['conda_env']} && "
            f"cd {Path(config['export_script_wsl']).parent.as_posix()} && "
            f"python export_monkey_patch.py --model {wsl_pt} --imgsz {imgsz}"
        )
        result = run_command(["wsl", "-d", config["wsl_distro"], "bash", "-lc", command_text], log_path, timeout=3600)
        search_roots = [pt.parent, task / "input", task / "onnx"]
    else:
        command = [
            "conda",
            "run",
            "-n",
            config["conda_env"],
            "python",
            str(export_script),
            "--model",
            str(pt),
            "--imgsz",
            str(imgsz),
        ]
        result = run_command(command, log_path, cwd=export_script.parent, timeout=3600)
        search_roots = [pt.parent, export_script.parent, task / "input", task / "onnx"]

    if not result.ok:
        return {
            "ok": False,
            "error": "ONNX 导出失败",
            "command": result.command,
            "result": result.to_dict(),
            "log_path": str(log_path),
            "diagnosis": diagnose_file(log_path),
        }

    onnx_source = _find_exported_onnx(search_roots, pt.stem, started_at)
    if not onnx_source:
        message = "导出命令成功，但没有找到生成的 ONNX 文件。"
        append_log(log_path, message)
        return {
            "ok": False,
            "error": message,
            "command": result.command,
            "result": result.to_dict(),
            "log_path": str(log_path),
            "diagnosis": diagnose_text(message),
        }

    onnx_target = task / "onnx" / f"{pt.stem}.onnx"
    safe_copy(onnx_source, onnx_target)
    append_log(log_path, f"ONNX copied to {onnx_target}")
    return {
        "ok": True,
        "onnx_path": str(onnx_target),
        "source_onnx_path": str(onnx_source),
        "command": result.command,
        "result": result.to_dict(),
        "log_path": str(log_path),
        "diagnosis": [],
    }
