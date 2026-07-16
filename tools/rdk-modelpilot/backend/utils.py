from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from path_utils import ensure_dir, safe_copy


BASE_DIR = Path(os.environ.get("RDK_MODELPILOT_DATA_DIR", "")).resolve() if os.environ.get("RDK_MODELPILOT_DATA_DIR") else (
    Path.cwd() if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
)
LOG_DIR = BASE_DIR / "logs"
ensure_dir(LOG_DIR)


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    log_path: str
    duration_sec: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "log_path": self.log_path,
            "duration_sec": self.duration_sec,
        }


def now_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def append_log(path: str | Path, message: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with target.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(f"[{timestamp}] {message.rstrip()}\n")


def command_to_text(command: list[str] | str) -> str:
    if isinstance(command, str):
        return command
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def run_command(
    command: list[str] | str,
    log_path: str | Path,
    cwd: str | Path | None = None,
    timeout: int | None = None,
    shell: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    text = command_to_text(command)
    append_log(log_path, f"$ {text}")
    start = time.time()
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            shell=shell,
            env=env,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        duration = time.time() - start
        if stdout:
            append_log(log_path, stdout.rstrip())
        if stderr:
            append_log(log_path, stderr.rstrip())
        append_log(log_path, f"exit={proc.returncode} duration={duration:.1f}s")
        return CommandResult(text, proc.returncode, stdout or "", stderr or "", str(log_path), duration)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        duration = time.time() - start
        append_log(log_path, f"TIMEOUT after {timeout}s")
        return CommandResult(text, 124, stdout or "", stderr or "", str(log_path), duration)
    except FileNotFoundError as exc:
        duration = time.time() - start
        append_log(log_path, f"FileNotFoundError: {exc}")
        return CommandResult(text, 127, "", str(exc), str(log_path), duration)
    except Exception as exc:  # noqa: BLE001 - external command wrapper must report all failures.
        duration = time.time() - start
        append_log(log_path, f"Exception: {exc}")
        return CommandResult(text, 1, "", str(exc), str(log_path), duration)


def quick_command(command: list[str] | str, timeout: int = 8, shell: bool = False) -> CommandResult:
    return run_command(command, LOG_DIR / "env_check_commands.log", timeout=timeout, shell=shell)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def find_conda_executable(config: dict[str, Any] | None = None) -> str | None:
    """Find Conda even when Anaconda did not add it to the Windows PATH."""
    configured = str((config or {}).get("conda_executable", "")).strip()
    candidates = [configured, os.environ.get("CONDA_EXE", ""), shutil.which("conda") or ""]

    home = Path.home()
    local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    for root in [
        home / "anaconda3",
        home / "miniconda3",
        Path("C:/ProgramData/anaconda3"),
        local_app_data / "anaconda3",
        local_app_data / "miniconda3",
    ]:
        candidates.append(str(root / "Scripts" / "conda.exe"))

    for drive in ["C", "D", "E"]:
        for name in ["ANACONDA", "Anaconda3", "anaconda3", "Miniconda3", "miniconda3"]:
            candidates.append(str(Path(f"{drive}:/") / name / "Scripts" / "conda.exe"))

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return None


def status(name: str, ok: bool, detail: str = "", level: str | None = None, data: Any = None) -> dict[str, Any]:
    if level is None:
        level = "ok" if ok else "error"
    return {
        "name": name,
        "ok": ok,
        "level": level,
        "detail": detail,
        "data": data,
    }


def read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8", errors="ignore") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}
    return data


def parse_data_yaml(path: str | Path | None, manual_classes: list[str] | None = None) -> dict[str, Any]:
    fallback_names = [str(name).strip() for name in (manual_classes or []) if str(name).strip()]
    if path and Path(path).exists():
        selected_path = Path(path).resolve()
        data = read_yaml(selected_path)
        selected_raw = data
        resolved_data_yaml_path = ""

        # Ultralytics run folders contain args.yaml. It points to the real
        # dataset YAML through the `data` key but has no nc/names of its own.
        if not data.get("names") and isinstance(data.get("data"), str):
            referenced = Path(str(data["data"]))
            if not referenced.is_absolute():
                referenced = (selected_path.parent / referenced).resolve()
            if referenced.is_file() and referenced.resolve() != selected_path:
                referenced_data = read_yaml(referenced)
                if referenced_data.get("names"):
                    data = referenced_data
                    resolved_data_yaml_path = str(referenced.resolve())
        names = data.get("names", [])
        if isinstance(names, dict):
            ordered = [str(names[key]) for key in sorted(names, key=lambda item: int(item) if str(item).isdigit() else str(item))]
        elif isinstance(names, list):
            ordered = [str(item) for item in names]
        else:
            ordered = []

        # Some training YAML files omit names or leave nc at zero. Keep the
        # explicitly entered class list usable instead of blocking conversion.
        if not ordered and fallback_names:
            ordered = fallback_names
        try:
            nc = int(data.get("nc")) if data.get("nc") is not None else len(ordered)
        except (TypeError, ValueError):
            nc = len(ordered)
        if nc <= 0 and ordered:
            nc = len(ordered)
        validation = validate_class_names(ordered, nc)
        return {
            "path": str(selected_path),
            "resolved_data_yaml_path": resolved_data_yaml_path,
            "nc": nc,
            "names": ordered,
            "raw": data,
            "selected_raw": selected_raw if resolved_data_yaml_path else None,
            "validation": validation,
        }
    names = fallback_names or ["person", "helmet", "reflective_vest"]
    validation = validate_class_names(names, len(names))
    return {"path": "", "nc": len(names), "names": names, "raw": {"nc": len(names), "names": names}, "validation": validation}


def resolve_dataset_image_dir(data_yaml_path: str | Path | None) -> str:
    """Resolve a usable calibration image folder from a YOLO data.yaml."""
    if not data_yaml_path or not Path(data_yaml_path).is_file():
        return ""
    yaml_path = Path(data_yaml_path).resolve()
    data = read_yaml(yaml_path)
    if not any(data.get(key) for key in ["val", "train", "test"]) and isinstance(data.get("data"), str):
        referenced = Path(str(data["data"]))
        if not referenced.is_absolute():
            referenced = (yaml_path.parent / referenced).resolve()
        if referenced.is_file():
            yaml_path = referenced.resolve()
            data = read_yaml(yaml_path)
    dataset_root_value = data.get("path", "")
    dataset_root = Path(str(dataset_root_value)) if dataset_root_value else yaml_path.parent
    if not dataset_root.is_absolute():
        dataset_root = (yaml_path.parent / dataset_root).resolve()

    for key in ["val", "train", "test"]:
        value = data.get(key)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not item:
                continue
            candidate = Path(str(item))
            if not candidate.is_absolute():
                candidate = dataset_root / candidate
            if candidate.is_dir():
                return str(candidate.resolve())
    return ""


def validate_class_names(names: list[str], nc: int | None = None) -> dict[str, Any]:
    class_count = int(nc if nc is not None else len(names))
    errors: list[str] = []
    warnings: list[str] = []
    if class_count < 1 or class_count > 10:
        errors.append("当前 MVP 支持 1 到 10 个检测类别。")
    if len(names) != class_count:
        errors.append(f"data.yaml 中 nc={class_count}，但 names 数量为 {len(names)}。")
    if any(not str(name).strip() for name in names):
        errors.append("类别名称不能为空。")
    if len(set(names)) != len(names):
        warnings.append("类别名称存在重复，可能导致部署端类别显示混乱。")
    return {
        "ok": not errors,
        "class_count": class_count,
        "supported_range": [1, 10],
        "errors": errors,
        "warnings": warnings,
    }


def create_task_dir(output_dir: str | Path, model_path: str | Path) -> Path:
    model_name = Path(model_path).stem or "model"
    safe_name = "".join(ch if ch.isalnum() or ch in ["_", "-"] else "_" for ch in model_name)
    task_dir = ensure_dir(Path(output_dir) / f"{safe_name}_{now_slug()}")
    for child in ["input", "onnx", "bin", "calibration/selected_images", "reports", "configs", "logs"]:
        ensure_dir(task_dir / child)
    return task_dir


def copy_inputs_to_task(task_dir: str | Path, pt_path: str | Path, data_yaml_path: str | Path | None = None) -> dict[str, str]:
    target = Path(task_dir)
    result = {"pt": str(safe_copy(pt_path, target / "input" / Path(pt_path).name))}
    if data_yaml_path and Path(data_yaml_path).exists():
        result["data_yaml"] = str(safe_copy(data_yaml_path, target / "input" / Path(data_yaml_path).name))
    return result


def file_info(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    stat = target.stat()
    return {
        "path": str(target),
        "name": target.name,
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / 1024 / 1024, 3),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def write_json(path: str | Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_text_tail(path: str | Path, max_chars: int = 20000) -> str:
    target = Path(path)
    if not target.exists():
        return ""
    text = target.read_text(encoding="utf-8", errors="ignore")
    return text[-max_chars:]


def platform_info() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
    }
