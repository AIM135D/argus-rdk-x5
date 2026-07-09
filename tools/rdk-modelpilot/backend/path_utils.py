from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath


def normalize_path(path: str | os.PathLike | None) -> str:
    if not path:
        return ""
    text = str(path).strip().strip('"')
    if not text:
        return ""
    return str(Path(text).expanduser())


def windows_to_wsl_path(path: str | os.PathLike | None) -> str:
    if not path:
        return ""
    text = str(path).strip().strip('"').replace("/", "\\")
    if text.startswith("\\\\"):
        # UNC paths are not safely mappable into WSL without a mounted share.
        return text
    drive, tail = os.path.splitdrive(text)
    if not drive:
        return str(PurePosixPath(str(path).replace("\\", "/")))
    drive_letter = drive[0].lower()
    tail = tail.replace("\\", "/").lstrip("/")
    return f"/mnt/{drive_letter}/{tail}"


def wsl_to_windows_path(path: str | os.PathLike | None) -> str:
    if not path:
        return ""
    text = str(path).strip().strip('"')
    parts = PurePosixPath(text).parts
    if len(parts) >= 4 and parts[0] == "/" and parts[1] == "mnt" and len(parts[2]) == 1:
        drive = parts[2].upper() + ":"
        tail = "\\".join(parts[3:])
        return f"{drive}\\{tail}" if tail else f"{drive}\\"
    return text.replace("/", "\\")


def docker_mount_path_from_wsl(path: str | os.PathLike, mount_root: str = "/workspace") -> str:
    text = str(path).strip().replace("\\", "/")
    name = PurePosixPath(text).name
    return f"{mount_root}/{name}"


def ensure_dir(path: str | os.PathLike) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_copy(src: str | os.PathLike, dst: str | os.PathLike) -> Path:
    source = Path(src)
    target = Path(dst)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.resolve() == target.resolve():
            return target
    except OSError:
        pass
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    return target


def contains_risky_characters(path: str | os.PathLike) -> bool:
    text = str(path)
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return True
    return " " in text or any(ch in text for ch in ["(", ")", "&", "^", "%"])
