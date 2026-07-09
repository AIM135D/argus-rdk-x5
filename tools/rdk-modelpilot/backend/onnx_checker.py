from __future__ import annotations

from pathlib import Path
from typing import Any

from error_diagnoser import diagnose_text


WARNING_TEXT = (
    "当前 ONNX 不符合 RDK X5 六输出 DFL 后处理结构，直接量化或接入旧后处理可能导致无框、框偏移、类别错乱或误检异常。"
)


def _dims(value_info: Any) -> list[int | str]:
    dims: list[int | str] = []
    tensor_type = value_info.type.tensor_type
    for dim in tensor_type.shape.dim:
        if dim.dim_value:
            dims.append(int(dim.dim_value))
        elif dim.dim_param:
            dims.append(str(dim.dim_param))
        else:
            dims.append("?")
    return dims


def _initializer_names(graph: Any) -> set[str]:
    return {item.name for item in graph.initializer}


def _has_dim(shape: list[int | str], value: int) -> bool:
    return any(isinstance(dim, int) and dim == value for dim in shape)


def _spatial_scale(shape: list[int | str]) -> int | None:
    for scale in [80, 40, 20]:
        if sum(1 for dim in shape if dim == scale) >= 2:
            return scale
    return None


def _channel_candidates(shape: list[int | str]) -> list[int]:
    candidates: list[int] = []
    if len(shape) >= 4:
        for dim in [shape[1], shape[-1]]:
            if isinstance(dim, int) and dim != 1:
                candidates.append(dim)
    candidates.extend(dim for dim in shape if isinstance(dim, int) and dim not in {1, 20, 40, 80})
    return list(dict.fromkeys(candidates))


def _classify_output(shape: list[int | str], classes: int) -> dict[str, Any]:
    scale = _spatial_scale(shape)
    channels = _channel_candidates(shape)
    branch = "unknown"
    reg_max = None
    if classes in channels:
        branch = "cls"
    if 64 in channels:
        branch = "box"
        reg_max = 16
    return {"shape": shape, "scale": scale, "branch": branch, "channels": channels, "reg_max": reg_max}


def _input_ok(shape: list[int | str], imgsz: int) -> tuple[bool, str]:
    if len(shape) != 4:
        return False, f"输入维度不是 4 维：{shape}"
    channel_ok = shape[1] in [3, "?", "batch", "dynamic"] or shape[1] == "channel"
    spatial = [shape[2], shape[3]]
    spatial_ok = all(dim == imgsz or isinstance(dim, str) or dim == "?" for dim in spatial)
    if channel_ok and spatial_ok:
        return True, f"输入 shape 可接受：{shape}"
    return False, f"期望 1x3x{imgsz}x{imgsz} 或可推断动态输入，实际：{shape}"


def check_onnx_structure(
    onnx_path: str | Path,
    classes: int,
    task_dir: str | Path | None = None,
    imgsz: int = 640,
) -> dict[str, Any]:
    target = Path(onnx_path)
    report_path = Path(task_dir) / "reports" / "onnx_structure_report.md" if task_dir else target.with_suffix(".onnx_structure_report.md")
    if not target.exists():
        message = f"ONNX 文件不存在：{target}"
        result = {"ok": False, "error": message, "diagnosis": diagnose_text(message), "report_path": str(report_path)}
        write_onnx_report(result, report_path)
        return result

    try:
        import onnx  # type: ignore
    except Exception as exc:
        message = f"当前 Python 环境缺少 onnx，无法检查结构：{exc}"
        result = {"ok": False, "error": message, "diagnosis": diagnose_text(message), "report_path": str(report_path)}
        write_onnx_report(result, report_path)
        return result

    try:
        model = onnx.load(str(target))
        try:
            model = onnx.shape_inference.infer_shapes(model)
        except Exception:
            pass
        graph = model.graph
        init_names = _initializer_names(graph)
        inputs = [item for item in graph.input if item.name not in init_names]
        outputs = list(graph.output)
        input_infos = [{"name": item.name, "shape": _dims(item)} for item in inputs]
        output_infos = [{"name": item.name, "shape": _dims(item)} for item in outputs]
    except Exception as exc:  # noqa: BLE001
        message = f"ONNX 读取失败：{exc}"
        result = {"ok": False, "error": message, "diagnosis": diagnose_text(message), "report_path": str(report_path)}
        write_onnx_report(result, report_path)
        return result

    checks: list[dict[str, Any]] = []
    checks.append({"name": "输入节点数量", "ok": len(input_infos) == 1, "detail": f"{len(input_infos)}"})
    if input_infos:
        ok, detail = _input_ok(input_infos[0]["shape"], imgsz)
        checks.append({"name": "输入 shape", "ok": ok, "detail": detail})
    checks.append({"name": "输出数量", "ok": len(output_infos) == 6, "detail": f"{len(output_infos)}"})

    classified = [_classify_output(item["shape"], classes) for item in output_infos]
    expected = [
        ("cls", 80),
        ("box", 80),
        ("cls", 40),
        ("box", 40),
        ("cls", 20),
        ("box", 20),
    ]
    order_ok = len(classified) == 6
    for index, (branch, scale) in enumerate(expected):
        if index >= len(classified):
            order_ok = False
            continue
        item = classified[index]
        item_ok = item["branch"] == branch and item["scale"] == scale
        checks.append(
            {
                "name": f"输出 {index} {branch} {scale}x{scale}",
                "ok": item_ok,
                "detail": f"shape={item['shape']} branch={item['branch']} scale={item['scale']}",
            }
        )
        order_ok = order_ok and item_ok

    reg_ok = all(item["reg_max"] == 16 for item in classified if item["branch"] == "box")
    cls_ok = all(classes in item["channels"] for item in classified if item["branch"] == "cls")
    checks.append({"name": "reg_max", "ok": reg_ok and len([i for i in classified if i["branch"] == "box"]) == 3, "detail": "期望 box 通道 64，即 reg_max=16"})
    checks.append({"name": "classes", "ok": cls_ok and len([i for i in classified if i["branch"] == "cls"]) == 3, "detail": f"期望分类通道={classes}"})
    checks.append({"name": "输出顺序", "ok": order_ok, "detail": "cls outputs: [0, 2, 4], box outputs: [1, 3, 5]"})

    suspected = []
    if len(output_infos) == 1:
        shape = output_infos[0]["shape"]
        if _has_dim(shape, 25200) or any(isinstance(dim, int) and dim in {classes + 5, classes + 85} for dim in shape):
            suspected.append("疑似旧 YOLOv5 anchor 输出结构")
        else:
            suspected.append("疑似普通 Ultralytics export 单输出结构")
    if len(output_infos) not in {1, 6}:
        suspected.append("输出数量异常，可能不是 rdk_model_zoo YOLO DFL 导出结果")

    ok = all(item["ok"] for item in checks)
    result = {
        "ok": ok,
        "onnx_path": str(target),
        "inputs": input_infos,
        "outputs": output_infos,
        "classified_outputs": classified,
        "checks": checks,
        "suspected": suspected,
        "warning": "" if ok else WARNING_TEXT,
        "report_path": str(report_path),
        "diagnosis": [] if ok else diagnose_text("ONNX output is not 6 or structure mismatch"),
    }
    write_onnx_report(result, report_path)
    return result


def write_onnx_report(result: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# ONNX 结构检查报告", ""]
    if "error" in result:
        lines.append(f"- 结果：失败")
        lines.append(f"- 错误：{result['error']}")
    else:
        lines.append(f"- ONNX：{result['onnx_path']}")
        lines.append(f"- 结论：{'通过' if result['ok'] else '不通过'}")
        if result.get("warning"):
            lines.append(f"- 重要提示：{result['warning']}")
        lines.append("")
        lines.append("## 输入")
        for item in result.get("inputs", []):
            lines.append(f"- {item['name']}: {item['shape']}")
        lines.append("")
        lines.append("## 输出")
        for index, item in enumerate(result.get("outputs", [])):
            lines.append(f"- {index}. {item['name']}: {item['shape']}")
        lines.append("")
        lines.append("## 检查项")
        for item in result.get("checks", []):
            icon = "OK" if item["ok"] else "FAIL"
            lines.append(f"- {icon} {item['name']}: {item['detail']}")
        if result.get("suspected"):
            lines.append("")
            lines.append("## 疑似问题")
            lines.extend(f"- {item}" for item in result["suspected"])
    lines.append("")
    lines.append(
        "当前 ONNX 如果不符合 RDK X5 六输出 DFL 后处理结构，直接量化或接入旧后处理可能导致无框、框偏移、类别错乱或误检异常。"
    )
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
