from __future__ import annotations

from pathlib import Path
from typing import Any


OLD_POSTPROCESS_WARNING = (
    "该模型不能直接套用旧式 YOLOv5 anchor 后处理、Yolov5PostProcess、Yolov5doProcess 或 libpostprocess.so "
    "的旧检测链，否则可能出现无框、框偏移、类别错误或误检异常。"
)


def _ok_text(value: Any) -> str:
    return "通过" if bool(value) else "未通过"


def generate_deploy_report(
    task_dir: str | Path,
    model_path: str | Path,
    data_yaml: dict[str, Any],
    config: dict[str, Any],
    onnx_result: dict[str, Any] | None = None,
    quant_result: dict[str, Any] | None = None,
    calibration_result: dict[str, Any] | None = None,
    deploy_config_path: str | Path | None = None,
) -> dict[str, Any]:
    task = Path(task_dir)
    report_path = task / "reports" / "deploy_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    names = data_yaml.get("names", [])
    onnx_result = onnx_result or {}
    quant_result = quant_result or {}
    calibration_result = calibration_result or {}

    bin_path = quant_result.get("bin_path", "")
    lines = [
        "# RDK ModelPilot 部署报告",
        "",
        "## 项目概览",
        f"- 项目名称：RDK ModelPilot",
        f"- 模型文件名：{Path(model_path).name}",
        f"- 输入 .pt 路径：{model_path}",
        f"- ONNX 输出路径：{onnx_result.get('onnx_path', '')}",
        f"- BIN 输出路径：{bin_path}",
        f"- deploy_config.py：{deploy_config_path or ''}",
        f"- 输入尺寸：{config.get('default_imgsz', 640)} x {config.get('default_imgsz', 640)}",
        f"- 目标平台：{config.get('target', 'RDK X5 bayes-e')}",
        f"- 运行时输入格式：{config.get('runtime_input', 'NV12')}",
        "",
        "## 类别",
        f"- nc：{data_yaml.get('nc', len(names))}",
    ]
    for index, name in enumerate(names):
        lines.append(f"- {index}: {name}")

    lines.extend(
        [
            "",
            "## 输出结构",
            f"- ONNX 六输出 DFL 检查：{_ok_text(onnx_result.get('ok'))}",
            "- 期望分类输出：80x80xclasses, 40x40xclasses, 20x20xclasses",
            "- 期望回归输出：80x80x64, 40x40x64, 20x20x64",
            "- 输出顺序：cls outputs [0, 2, 4], box outputs [1, 3, 5]",
            "- reg_max：16",
            "",
            "## 量化编译",
            f"- hb_mapper checker：{_ok_text(quant_result.get('ok'))}",
            f"- .bin 生成：{_ok_text(bool(bin_path))}",
            f"- quant_config.yaml：{quant_result.get('quant_config_path', '')}",
            f"- checker.log：{quant_result.get('checker_log', '')}",
            f"- makertbin.log：{quant_result.get('makertbin_log', '')}",
            "",
            "## 校准集",
            f"- 校准图片数量：{calibration_result.get('total_images', 0)}",
            f"- 已用于量化图片：{calibration_result.get('selected_count', 0)}",
            f"- 平均亮度：{calibration_result.get('average_brightness')}",
        ]
    )
    suggestions = calibration_result.get("summary", {}).get("suggestions", [])
    if suggestions:
        lines.append("- 校准集质量建议：")
        lines.extend(f"  - {item}" for item in suggestions)

    lines.extend(
        [
            "",
            "## 推荐板端后处理参数",
            "- POSTPROCESS_TYPE = YOLO_DFL_6_OUTPUT",
            "- STRIDES = [8, 16, 32]",
            "- REG = 16",
            "- CLS_OUTPUTS = [0, 2, 4]",
            "- BOX_OUTPUTS = [1, 3, 5]",
            f"- CLASSES_NUM = {len(names)}",
            "",
            "## 推荐板端依赖",
            "- hobot_dnn 或 pyeasy_dnn",
            "- hrt_model_exec",
            "- 与 RDK X5 系统版本匹配的 D-Robotics runtime",
            "",
            "## 重要提醒",
            OLD_POSTPROCESS_WARNING,
            "",
            "## 常见错误提示",
            "- 无框：优先检查 ONNX 是否为六输出 DFL、类别数是否一致、输出顺序是否正确。",
            "- 框偏移：检查输入 resize、padding、NV12/RGB 转换、后处理 stride 和 reg_max。",
            "- 类别错误：检查 data.yaml 类别顺序和 deploy_config.py 的 CLASS_NAMES。",
            "- makertbin 失败：检查 checker.log 中 unsupported op、输入 shape、校准图片目录。",
            "",
            "## 下一步部署命令",
            "```bash",
            "scp model.bin root@<RDK_X5_IP>:/userdata/model.bin",
            "scp deploy_config.py root@<RDK_X5_IP>:/userdata/deploy_config.py",
            "ssh root@<RDK_X5_IP>",
            "hrt_model_exec model_info --model_file /userdata/model.bin",
            "hrt_model_exec perf --model_file /userdata/model.bin",
            "```",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "deploy_report_path": str(report_path)}
