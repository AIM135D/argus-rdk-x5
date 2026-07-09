from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config_manager import load_config
from path_utils import contains_risky_characters
from utils import LOG_DIR, platform_info, quick_command, status


PYTHON_PACKAGES = {
    "ultralytics": "ultralytics",
    "torch": "torch",
    "torchvision": "torchvision",
    "onnx": "onnx",
    "onnxruntime": "onnxruntime",
    "numpy": "numpy",
    "opencv-python": "cv2",
    "scipy": "scipy",
    "pyyaml": "yaml",
}


def _clean_wsl_output(text: str) -> str:
    return text.replace("\x00", "").replace("\r", "")


def _parse_wsl_distros(text: str) -> list[dict[str, str]]:
    distros: list[dict[str, str]] = []
    cleaned = _clean_wsl_output(text)
    for line in cleaned.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name"):
            continue
        line = line.replace("*", " ").strip()
        parts = re.split(r"\s{2,}|\t+", line)
        if parts:
            distros.append(
                {
                    "name": parts[0],
                    "state": parts[1] if len(parts) > 1 else "",
                    "version": parts[2] if len(parts) > 2 else "",
                }
            )
    return distros


def _check_tool(command: list[str], display_name: str, timeout: int = 8) -> dict[str, Any]:
    result = quick_command(command, timeout=timeout)
    detail = (result.stdout or result.stderr).strip().splitlines()
    return status(display_name, result.ok, detail[0] if detail else f"exit={result.returncode}", data=result.to_dict())


def _conda_envs() -> tuple[list[str], dict[str, Any]]:
    result = quick_command(["conda", "env", "list", "--json"], timeout=12)
    if result.ok:
        try:
            payload = json.loads(result.stdout)
            envs = [Path(item).name for item in payload.get("envs", [])]
            return envs, result.to_dict()
        except json.JSONDecodeError:
            pass
    result = quick_command(["conda", "env", "list"], timeout=12)
    envs: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        envs.append(Path(line.split()[0]).name)
    return envs, result.to_dict()


def _check_conda_package(env_name: str, pip_name: str, module_name: str) -> dict[str, Any]:
    code = (
        "import importlib, sys; "
        f"m=importlib.import_module('{module_name}'); "
        "print(getattr(m, '__version__', 'installed'))"
    )
    result = quick_command(["conda", "run", "-n", env_name, "python", "-c", code], timeout=25)
    detail = (result.stdout or result.stderr).strip().splitlines()
    return status(pip_name, result.ok, detail[-1] if detail else f"exit={result.returncode}", data=result.to_dict())


def check_environment(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    docker_image = cfg["docker_image"]
    conda_env = cfg["conda_env"]
    expected_distro = cfg["wsl_distro"]
    warnings: list[str] = []
    errors: list[str] = []

    windows = {
        "version": status("Windows 版本", True, f"{platform_info()['release']} {platform_info()['version']}", data=platform_info()),
        "powershell": _check_tool(["powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"], "PowerShell"),
        "git": _check_tool(["git", "--version"], "Git"),
        "python": _check_tool(["python", "--version"], "Python"),
    }

    docker = {
        "cli": _check_tool(["docker", "--version"], "Docker CLI"),
    }
    docker["running"] = _check_tool(["docker", "info", "--format", "{{.ServerVersion}}"], "Docker Engine", timeout=10)
    docker["image"] = _check_tool(["docker", "image", "inspect", docker_image, "--format", "{{.Id}}"], f"OpenExplorer 镜像 {docker_image}", timeout=12)
    if docker["running"]["ok"] and docker["image"]["ok"]:
        docker["hb_mapper"] = _check_tool(["docker", "run", "--rm", docker_image, "hb_mapper", "--help"], "Docker hb_mapper", timeout=30)
        docker["hbdk_horizon_nn"] = _check_tool(
            [
                "docker",
                "run",
                "--rm",
                docker_image,
                "python3",
                "-c",
                "import importlib; print('hbdk=', bool(importlib.util.find_spec('hbdk4') or importlib.util.find_spec('hbdk'))); print('horizon_nn=', bool(importlib.util.find_spec('horizon_nn')))",
            ],
            "Docker hbdk / horizon_nn",
            timeout=30,
        )
    else:
        docker["hb_mapper"] = status("Docker hb_mapper", False, "Docker 未运行或镜像不存在，跳过容器内检查", level="warn")
        docker["hbdk_horizon_nn"] = status("Docker hbdk / horizon_nn", False, "Docker 未运行或镜像不存在，跳过容器内检查", level="warn")

    wsl_cmd = quick_command(["wsl", "-l", "-v"], timeout=12)
    distros = _parse_wsl_distros(wsl_cmd.stdout or wsl_cmd.stderr)
    distro_names = [item["name"] for item in distros]
    wsl = {
        "cli": status("WSL2", wsl_cmd.ok, _clean_wsl_output((wsl_cmd.stdout or wsl_cmd.stderr).strip()), data=wsl_cmd.to_dict()),
        "distros": status("WSL 发行版", bool(distros), ", ".join(distro_names) if distros else "未发现 WSL 发行版", data=distros, level="ok" if distros else "warn"),
        "expected_distro": status(
            f"默认发行版 {expected_distro}",
            expected_distro in distro_names,
            "已找到" if expected_distro in distro_names else f"未找到，当前可用：{', '.join(distro_names) or '无'}",
            data={"available": distro_names},
            level="ok" if expected_distro in distro_names else "warn",
        ),
    }

    conda: dict[str, Any] = {}
    conda_cli = _check_tool(["conda", "--version"], "Conda / Anaconda", timeout=8)
    if conda_cli["ok"]:
        conda["cli"] = conda_cli
        envs, env_result = _conda_envs()
        conda["env_list"] = status("Conda 环境列表", True, ", ".join(envs) if envs else "未解析到环境", data=env_result)
        conda["env_exists"] = status(f"Conda 环境 {conda_env}", conda_env in envs, "已存在" if conda_env in envs else "未找到")
        conda["python_version"] = _check_tool(["conda", "run", "-n", conda_env, "python", "--version"], f"{conda_env} Python")
    else:
        conda["cli"] = status(
            "Conda / Anaconda",
            False,
            "未在 PATH 中发现 conda。若环境装在 Anaconda Prompt 中，可直接用设置页保留环境名，转换时会按配置调用。",
            level="warn",
            data=conda_cli.get("data"),
        )
        conda["env_list"] = status("Conda 环境列表", False, "conda 不在 PATH，跳过可选检查", level="warn")
        conda["env_exists"] = status(f"Conda 环境 {conda_env}", False, "conda 不在 PATH，跳过可选检查", level="warn")
        conda["python_version"] = status(f"{conda_env} Python", False, "conda 不在 PATH，跳过可选检查", level="warn")

    python_packages = {}
    if conda.get("env_exists", {}).get("ok"):
        for pip_name, module_name in PYTHON_PACKAGES.items():
            python_packages[pip_name] = _check_conda_package(conda_env, pip_name, module_name)
    else:
        for pip_name in PYTHON_PACKAGES:
            python_packages[pip_name] = status(pip_name, False, f"Conda 环境 {conda_env} 不存在，跳过包检查", level="warn")

    rdk_paths = {
        "repo": cfg["rdk_model_zoo_windows"],
        "export_script": cfg["export_script_windows"],
        "mapper": cfg["mapper_windows"],
    }
    rdk_model_zoo = {}
    for key, path_text in rdk_paths.items():
        exists = Path(path_text).exists()
        rdk_model_zoo[key] = status(key, exists, path_text, level="ok" if exists else "error")
        if contains_risky_characters(path_text):
            warnings.append(f"{key} 路径包含中文、空格或特殊字符，WSL/Docker 脚本可能解析失败：{path_text}")

    optional_sections = {"conda", "python_packages"}
    for section_name, section in [
        ("windows", windows),
        ("wsl", wsl),
        ("docker", docker),
        ("conda", conda),
        ("python_packages", python_packages),
        ("rdk_model_zoo", rdk_model_zoo),
    ]:
        for item in section.values():
            if isinstance(item, dict):
                if item.get("level") == "error":
                    if section_name in optional_sections:
                        warnings.append(f"{section_name}: {item.get('name')} - {item.get('detail')}")
                    else:
                        errors.append(f"{section_name}: {item.get('name')} - {item.get('detail')}")
                elif item.get("level") == "warn":
                    warnings.append(f"{section_name}: {item.get('name')} - {item.get('detail')}")

    payload = {
        "windows": windows,
        "wsl": wsl,
        "conda": conda,
        "docker": docker,
        "rdk_model_zoo": rdk_model_zoo,
        "python_packages": python_packages,
        "summary": {
            "ok": not errors,
            "warnings": warnings,
            "errors": errors,
        },
    }
    report_path = write_env_report(payload)
    payload["report_path"] = str(report_path)
    return payload


def write_env_report(payload: dict[str, Any]) -> Path:
    report = LOG_DIR / "env_check_report.md"
    lines = [
        "# RDK ModelPilot 环境检测报告",
        "",
        f"- 结论：{'通过' if payload['summary']['ok'] else '存在问题'}",
        f"- 错误数量：{len(payload['summary']['errors'])}",
        f"- 警告数量：{len(payload['summary']['warnings'])}",
        "",
    ]
    for section_name in ["windows", "wsl", "conda", "docker", "rdk_model_zoo", "python_packages"]:
        lines.append(f"## {section_name}")
        section = payload.get(section_name, {})
        for key, item in section.items():
            icon = {"ok": "OK", "warn": "WARN", "error": "FAIL"}.get(item.get("level"), "INFO")
            lines.append(f"- {icon} **{item.get('name', key)}**: {item.get('detail', '')}")
        lines.append("")
    if payload["summary"]["errors"]:
        lines.append("## 错误")
        lines.extend(f"- {item}" for item in payload["summary"]["errors"])
        lines.append("")
    if payload["summary"]["warnings"]:
        lines.append("## 警告")
        lines.extend(f"- {item}" for item in payload["summary"]["warnings"])
        lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
