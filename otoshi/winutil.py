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


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    """Command line that starts this Otoshi installation (exe, or pythonw + main.py from source)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    script = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{interpreter}" "{script}"'


def set_autostart(name: str, enabled: bool) -> bool:
    """Add or remove the per-user "run at sign-in" entry. Returns False on failure."""
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        logger.exception("Could not update the autostart entry")
        return False


def play_finish_sound() -> None:
    if IS_WINDOWS:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            logger.debug("Could not play sound", exc_info=True)
