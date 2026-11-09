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

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
ERROR_ALREADY_EXISTS = 183
SPI_GETWORKAREA = 0x0030

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


def make_click_through(hwnd: int) -> None:
    """Let mouse events pass through a window (used by the status overlay)."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
    except Exception:
        logger.debug("Could not make window click-through", exc_info=True)


def toplevel_hwnd(widget) -> int:
    """HWND of the native top-level window that hosts a Tk widget."""
    if not IS_WINDOWS:
        return 0
    try:
        return int(ctypes.windll.user32.GetParent(widget.winfo_id()))
    except Exception:
        return 0


def virtual_screen(fallback: Optional[Rect] = None) -> Rect:
    """Bounding box of all monitors in physical pixels."""
    if IS_WINDOWS:
        try:
            gsm = ctypes.windll.user32.GetSystemMetrics
            x, y, w, h = gsm(76), gsm(77), gsm(78), gsm(79)
            if w > 0 and h > 0:
                return x, y, x + w, y + h
        except Exception:
            pass
    return fallback or (0, 0, 1920, 1080)


def work_area(fallback: Rect) -> Rect:
    """Primary monitor area excluding the taskbar."""
    if IS_WINDOWS:
        try:
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
    return fallback


def open_folder(path: Path) -> None:
    if IS_WINDOWS:
        os.startfile(str(path))  # noqa: S606 - opening a local folder in Explorer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
