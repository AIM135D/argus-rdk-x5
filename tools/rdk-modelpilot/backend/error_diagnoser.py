from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Diagnosis:
    code: str
    reason: str
    suggestion: str
    command: str


PATTERNS: list[tuple[list[str], Diagnosis]] = [
    (
        ["docker", "is the docker daemon running"],
        Diagnosis(
            "DOCKER_NOT_RUNNING",
            "Docker 服务没有启动，OpenExplorer 容器无法运行。",
            "启动 Docker Desktop，等待左下角显示 Docker Engine running 后重试。",
            "Start-Process \"Docker Desktop\"",
        ),
    ),
    (
        ["wsl", "not found"],
        Diagnosis(
            "WSL_NOT_FOUND",
            "当前系统没有可用 WSL，或者 wsl.exe 无法访问。",
            "启用 WSL2 并安装 Ubuntu，必要时重启 Windows。",
            "wsl --install -d Ubuntu-22.04",
        ),
    ),
    (
        ["conda", "could not find environment", "environmentname"],
        Diagnosis(
            "CONDA_ENV_MISSING",
            "指定的 Conda 环境不存在。",
            "创建 yolo 环境并安装导出依赖。",
            "conda create -n yolo python=3.10 -y",
        ),
    ),
    (
        ["export_monkey_patch.py", "no such file"],
        Diagnosis(
            "EXPORT_SCRIPT_MISSING",
            "没有找到 D-Robotics 官方 export_monkey_patch.py。",
            "检查 rdk_model_zoo 路径，或重新克隆官方仓库。",
            "git clone https://github.com/D-Robotics/rdk_model_zoo.git D:\\rdk_model_zoo-main",
        ),
    ),
    (
        ["mapper.py", "no such file"],
        Diagnosis(
            "MAPPER_SCRIPT_MISSING",
            "没有找到 rdk_model_zoo 中的 mapper.py。",
            "检查 SettingsPage 中 mapper.py 路径，确认仓库完整。",
            "dir D:\\rdk_model_zoo-main\\samples\\vision\\ultralytics_yolo\\x86\\mapper.py",
        ),
    ),
    (
        ["modulenotfounderror", "no module named"],
        Diagnosis(
            "PYTHON_PACKAGE_MISSING",
            "Python 依赖缺失，当前 Conda 环境无法执行导出或检查。",
            "在 yolo 环境中安装 ultralytics、torch、onnx 等依赖。",
            "conda run -n yolo python -m pip install ultralytics torch torchvision onnx onnxruntime numpy opencv-python scipy pyyaml",
        ),
    ),
    (
        ["output", "6"],
        Diagnosis(
            "ONNX_NOT_SIX_OUTPUT",
            "ONNX 输出结构不是 RDK X5 YOLO DFL 六输出格式。",
            "使用 rdk_model_zoo 官方 export_monkey_patch.py 重新导出，不要使用普通 Ultralytics export。",
            "conda run -n yolo python D:\\rdk_model_zoo-main\\samples\\vision\\ultralytics_yolo\\x86\\export_monkey_patch.py --model D:\\path\\best.pt --imgsz 640",
        ),
    ),
    (
        ["unsupported op"],
        Diagnosis(
            "UNSUPPORTED_OP",
            "OpenExplorer checker 发现不支持的 ONNX 算子。",
            "确认模型结构是否为受支持 YOLO 检测模型，必要时简化网络或更新工具链。",
            "hb_mapper checker --model-type onnx --march bayes-e --proto model.onnx",
        ),
    ),
    (
        ["calibration", "empty"],
        Diagnosis(
            "EMPTY_CALIBRATION",
            "校准图片目录为空或没有 jpg/png/jpeg 图片。",
            "准备 20 到 50 张真实部署场景图片作为校准集。",
            "dir D:\\RDK_ModelPilot_Output\\your_task\\calibration\\selected_images",
        ),
    ),
    (
        ["makertbin", "failed"],
        Diagnosis(
            "MAKERTBIN_FAILED",
            "hb_mapper makertbin 量化编译失败。",
            "查看 makertbin.log 中首个 ERROR，优先排查 ONNX 结构、校准数据和配置文件。",
            "hb_mapper makertbin --config quant_config.yaml --model-type onnx",
        ),
    ),
    (
        ["access is denied"],
        Diagnosis(
            "PERMISSION_DENIED",
            "路径或命令权限不足。",
            "换用可写输出目录，或用管理员权限执行生成的 PowerShell 修复脚本。",
            "Start-Process powershell -Verb RunAs",
        ),
    ),
    (
        ["yolov5postprocess", "anchor"],
        Diagnosis(
            "OLD_YOLO_POSTPROCESS",
            "日志中出现旧式 YOLOv5 anchor 后处理链路，可能与 DFL 六输出模型不匹配。",
            "板端后处理应使用 YOLO DFL 六输出配置，类别和输出顺序必须与 deploy_config.py 一致。",
            "python deploy_config.py",
        ),
    ),
]


def diagnose_text(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    results: list[Diagnosis] = []
    for keywords, diagnosis in PATTERNS:
        if all(keyword.lower() in lowered for keyword in keywords):
            results.append(diagnosis)
    if any(ord(ch) > 127 for ch in text) or " " in text:
        if any(fragment in lowered for fragment in ["path", "file", "no such", "not found", "failed"]):
            results.append(
                Diagnosis(
                    "RISKY_PATH",
                    "路径可能包含中文、空格或特殊字符，部分 WSL/Docker/旧脚本参数解析会失败。",
                    "建议把模型、输出目录和 rdk_model_zoo 放在纯英文、无空格路径下。",
                    "D:\\RDK_ModelPilot_Output",
                )
            )
    if not results and text.strip():
        results.append(
            Diagnosis(
                "UNKNOWN_ERROR",
                "未匹配到内置错误类型，需要查看完整日志定位。",
                "优先检查日志中第一个 ERROR/Traceback/failed 行，并确认外部工具链版本。",
                "Get-Content logs\\app.log -Tail 200",
            )
        )
    return [asdict(item) for item in results]


def diagnose_file(path: str | Path) -> list[dict[str, str]]:
    target = Path(path)
    if not target.exists():
        return []
    return diagnose_text(target.read_text(encoding="utf-8", errors="ignore"))


def format_diagnoses(items: Iterable[dict[str, str]]) -> str:
    lines = []
    for item in items:
        lines.append(f"- [{item['code']}] {item['reason']}")
        lines.append(f"  建议：{item['suggestion']}")
        lines.append(f"  命令：`{item['command']}`")
    return "\n".join(lines)
