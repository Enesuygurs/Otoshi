"""Small Windows integration helpers. All of them degrade gracefully elsewhere."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from .logger import logger

IS_WINDOWS = os.name == "nt"

ERROR_ALREADY_EXISTS = 183

Rect = Tuple[int, int, int, int]  # left, top, right, bottom

_instance_mutex = None


def set_app_user_model_id(app_id: str) -> None:
    """Group the window under its own taskbar icon instead of python.exe's."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:  # pragma: no cover - cosmetic only
        logger.debug("SetCurrentProcessExplicitAppUserModelID failed", exc_info=True)


def acquire_single_instance(name: str) -> bool:
    """Return False if another Otoshi process already holds the named mutex.

    Two instances would both register the global hotkeys, so every key press
    would toggle twice.
    """
    global _instance_mutex
    if not IS_WINDOWS:
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True  # cannot tell; do not block startup
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _instance_mutex = handle
    return True


def open_folder(path: Path) -> None:
    if IS_WINDOWS:
        os.startfile(str(path))  # noqa: S606 - opening a local folder in Explorer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def cursor_pos() -> Optional[Tuple[int, int]]:
    """Cursor position in physical pixels (the coordinate space pynput uses)."""
    if not IS_WINDOWS:
        return None
    from ctypes import wintypes

    point = wintypes.POINT()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        return point.x, point.y
    return None


def window_rect(hwnd: int) -> Optional[Rect]:
    """Outer window rectangle in physical pixels."""
    if not IS_WINDOWS or not hwnd:
        return None
    from ctypes import wintypes

    rect = wintypes.RECT()
    if ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return rect.left, rect.top, rect.right, rect.bottom
    return None
