"""Filesystem locations used by the application."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from . import APP_NAME

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def asset(name: str) -> Path:
    """Return the path of a bundled asset (works from source and PyInstaller builds)."""
    return ASSETS_DIR / name


def data_dir() -> Path:
    """Per-user directory for settings and logs.

    ``OTOSHI_DATA_DIR`` overrides the location (useful for tests and portable setups).
    """
    override = os.environ.get("OTOSHI_DATA_DIR")
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_file() -> Path:
    return data_dir() / "config.json"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_config_files() -> List[Path]:
    """Places where Otoshi 1.x wrote ``otoshi_config.json`` (the working directory)."""
    candidates = [Path.cwd() / "otoshi_config.json"]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # 1.x was a single exe in dist/; 2.x is built as dist/Otoshi/Otoshi.exe.
        candidates += [exe_dir / "otoshi_config.json", exe_dir.parent / "otoshi_config.json"]
    seen, unique = set(), []
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique
