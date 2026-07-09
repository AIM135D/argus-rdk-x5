from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from path_utils import ensure_dir, safe_copy


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _image_files(folder: str | Path) -> list[Path]:
    root = Path(folder)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_images(files: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    unreadable: list[str] = []
    records: list[dict[str, Any]] = []
    try:
        import cv2  # type: ignore
    except Exception:
        for file in files:
            records.append({"path": str(file), "width": 0, "height": 0, "brightness": None, "readable": None})
        return records, ["当前 Python 环境缺少 opencv-python，已跳过亮度和分辨率精读。"]

    for file in files:
        image = cv2.imread(str(file))
        if image is None:
            unreadable.append(str(file))
            records.append({"path": str(file), "width": 0, "height": 0, "brightness": None, "readable": False})
            continue
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        records.append(
            {
                "path": str(file),
                "width": int(width),
                "height": int(height),
                "brightness": float(gray.mean()),
                "readable": True,
            }
        )
    return records, unreadable


def check_calibration_set(calibration_dir: str | Path, task_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(calibration_dir)
    files = _image_files(root)
    records, unreadable_or_notes = _inspect_images(files)
    warnings: list[str] = []
    errors: list[str] = []
    suggestions: list[str] = []

    if not root.exists():
        errors.append(f"校准图片目录不存在：{root}")
    if not files:
        errors.append("校准图片为空：未找到 jpg/png/jpeg 图片。")
        suggestions.append("请准备 20～50 张真实部署场景图片。")
    if len(files) < 20:
        warnings.append("校准图片少于 20 张。")
        suggestions.append("建议准备 20～50 张真实部署场景图片，覆盖目标尺寸、角度、光照和背景。")
    if len(files) > 50:
        warnings.append("校准图片超过 50 张。")
        suggestions.append("可以抽样 20～50 张高质量代表性图片，避免转换过慢。")

    if unreadable_or_notes:
        for item in unreadable_or_notes:
            if item.startswith("当前 Python 环境缺少"):
                warnings.append(item)
            else:
                warnings.append(f"存在无法读取图片：{item}")

    readable_records = [item for item in records if item.get("readable")]
    brightness_values = [float(item["brightness"]) for item in readable_records if item.get("brightness") is not None]
    dark_count = sum(1 for value in brightness_values if value < 35)
    bright_count = sum(1 for value in brightness_values if value > 220)
    if brightness_values:
        if dark_count / len(brightness_values) > 0.25:
            warnings.append("过暗图片比例较高。")
            suggestions.append("请补充正常光照图片，避免量化后低照场景误差被放大。")
        if bright_count / len(brightness_values) > 0.25:
            warnings.append("过曝图片比例较高。")
            suggestions.append("请补充曝光正常的图片，避免校准集分布偏离真实部署环境。")

    low_res_count = sum(1 for item in readable_records if item.get("width", 0) < 320 or item.get("height", 0) < 320)
    if readable_records and low_res_count / len(readable_records) > 0.2:
        warnings.append("分辨率过低图片比例较高。")
        suggestions.append("建议使用真实摄像头原始图片或接近部署分辨率的图片。")

    duplicate_hashes: Counter[str] = Counter()
    for file in files:
        try:
            duplicate_hashes[_md5(file)] += 1
        except OSError:
            pass
    duplicate_count = sum(count - 1 for count in duplicate_hashes.values() if count > 1)
    if files and duplicate_count / len(files) > 0.2:
        warnings.append("疑似大量重复图片。")
        suggestions.append("请减少重复样本，补充不同距离、角度、背景和光照的图片。")

    resolution_counter = Counter((item.get("width", 0), item.get("height", 0)) for item in readable_records)
    selected_dir = None
    selected_count = 0
    if task_dir and files:
        selected_dir = ensure_dir(Path(task_dir) / "calibration" / "selected_images")
        for file in files[:50]:
            safe_copy(file, selected_dir / file.name)
            selected_count += 1

    summary = {
        "ok": not errors,
        "warnings": warnings,
        "errors": errors,
        "suggestions": list(dict.fromkeys(suggestions)),
    }
    result = {
        "folder": str(root),
        "total_images": len(files),
        "jpg_png_jpeg_count": len(files),
        "selected_dir": str(selected_dir) if selected_dir else "",
        "selected_count": selected_count,
        "unreadable_count": len([item for item in records if item.get("readable") is False]),
        "duplicate_count": duplicate_count,
        "resolution_distribution": [
            {"width": width, "height": height, "count": count}
            for (width, height), count in resolution_counter.most_common(10)
        ],
        "average_brightness": round(mean(brightness_values), 2) if brightness_values else None,
        "dark_count": dark_count,
        "overexposed_count": bright_count,
        "summary": summary,
    }

    report_path = None
    if task_dir:
        report_path = Path(task_dir) / "reports" / "calibration_report.md"
    else:
        report_path = Path("logs") / "calibration_report.md"
    write_calibration_report(result, report_path)
    result["report_path"] = str(report_path)
    return result


def write_calibration_report(result: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 校准集质量检查报告",
        "",
        f"- 校准目录：{result['folder']}",
        f"- 图片数量：{result['total_images']}",
        f"- 已选择用于量化：{result.get('selected_count', 0)}",
        f"- 无法读取图片：{result['unreadable_count']}",
        f"- 疑似重复图片：{result['duplicate_count']}",
        f"- 平均亮度：{result['average_brightness']}",
        f"- 过暗图片数：{result['dark_count']}",
        f"- 过曝图片数：{result['overexposed_count']}",
        "",
        "## 分辨率分布",
    ]
    if result["resolution_distribution"]:
        for item in result["resolution_distribution"]:
            lines.append(f"- {item['width']}x{item['height']}: {item['count']} 张")
    else:
        lines.append("- 无可用分辨率数据")
    lines.append("")
    if result["summary"]["warnings"]:
        lines.append("## 警告")
        lines.extend(f"- {item}" for item in result["summary"]["warnings"])
        lines.append("")
    if result["summary"]["errors"]:
        lines.append("## 错误")
        lines.extend(f"- {item}" for item in result["summary"]["errors"])
        lines.append("")
    if result["summary"]["suggestions"]:
        lines.append("## 建议")
        lines.extend(f"- {item}" for item in result["summary"]["suggestions"])
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
