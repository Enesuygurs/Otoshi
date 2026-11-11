"""Global hotkeys via the Win32 ``RegisterHotKey`` API.

Compared with a keyboard hook this keeps working while an elevated
(administrator) window has focus, so a runaway clicker can always be stopped.
New combinations are captured with a short-lived pynput listener.

Hotkeys are stored as lower-case strings such as ``"ctrl+shift+f5"``.
"""

from __future__ import annotations

import ctypes
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Tuple

from .i18n import t
from .logger import logger
from .winutil import IS_WINDOWS

MODIFIER_ORDER = ("ctrl", "shift", "alt", "windows")
_MOD_FLAGS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "windows": 0x0008}
MOD_NOREPEAT = 0x4000
_MOD_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "left ctrl": "ctrl", "right ctrl": "ctrl",
    "shift": "shift", "left shift": "shift", "right shift": "shift",
    "alt": "alt", "left alt": "alt", "right alt": "alt", "alt gr": "alt",
    "windows": "windows", "win": "windows", "left windows": "windows", "right windows": "windows",
}  # fmt: skip
_MODIFIER_VKS = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "windows", 0x5C: "windows",
}  # fmt: skip


def _build_key_table() -> Dict[str, int]:
    keys: Dict[str, int] = {}
    for i in range(1, 25):
        keys[f"f{i}"] = 0x6F + i
    for c in "abcdefghijklmnopqrstuvwxyz":
        keys[c] = ord(c.upper())
    for d in "0123456789":
        keys[d] = ord(d)
        keys[f"num {d}"] = 0x60 + int(d)
    keys.update({
        "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08,
        "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "page up": 0x21, "page down": 0x22,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "print screen": 0x2C, "scroll lock": 0x91, "pause": 0x13, "caps lock": 0x14, "num lock": 0x90,
        "num multiply": 0x6A, "num add": 0x6B, "num subtract": 0x6D, "num decimal": 0x6E, "num divide": 0x6F,
        ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
        "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE, "menu": 0x5D,
    })  # fmt: skip
    return keys


VK_BY_NAME = _build_key_table()
NAME_BY_VK = {vk: name for name, vk in reversed(list(VK_BY_NAME.items()))}
_KEY_ALIASES = {
    "escape": "esc", "return": "enter", "del": "delete", "ins": "insert", "pgup": "page up", "pgdn": "page down",
    "page_up": "page up", "page_down": "page down", "print_screen": "print screen",
}  # fmt: skip
_TYPING_KEYS = (
    set("abcdefghijklmnopqrstuvwxyz0123456789;=,-./`[\\]'")
    | {"space", "enter", "tab", "backspace"}
    | {f"num {d}" for d in "0123456789"}
    | {"num multiply", "num add", "num subtract", "num decimal", "num divide"}
)


# ---------------------------------------------------------------------------
# Parsing / formatting / validation
# ---------------------------------------------------------------------------


def parse_hotkey(text: str) -> Optional[Tuple[FrozenSet[str], str]]:
    """``"Shift+Ctrl+F2"`` -> ``({"ctrl", "shift"}, "f2")``; ``None`` if unusable."""
    if not text:
        return None
    mods, keys = set(), []
    for raw in text.lower().split("+"):
        part = raw.strip()
        if not part:
            return None
        if part in _MOD_ALIASES:
            mods.add(_MOD_ALIASES[part])
        else:
            keys.append(_KEY_ALIASES.get(part, part))
    if len(keys) != 1 or keys[0] not in VK_BY_NAME:
        return None
    return frozenset(mods), keys[0]


def compose(mods: Iterable[str], key: str) -> str:
    present = set(mods)
    return "+".join([m for m in MODIFIER_ORDER if m in present] + [key])


def normalize_hotkey(text: str) -> str:
    parsed = parse_hotkey(text)
    return compose(*parsed) if parsed else text.strip().lower()


def format_hotkey(hotkey: str) -> str:
    """Human-friendly label: ``"ctrl+page up"`` -> ``"Ctrl+Page Up"``."""
    if not hotkey:
        return "—"
    labels = {"windows": "Win", "esc": "Esc"}
    return "+".join(labels.get(p) or (p.upper() if len(p) == 1 else p.title()) for p in hotkey.split("+"))


def validate_hotkey(hotkey: str) -> Optional[str]:
    """Return a (translated) error message, or ``None`` if the hotkey is usable."""
    if not hotkey:
        return t("hk_err_empty")
    parts = [p.strip() for p in hotkey.lower().split("+")]
    if parts and all(p in _MOD_ALIASES for p in parts):
        return t("hk_err_modifier_only")
    parsed = parse_hotkey(hotkey)
    if parsed is None:
        return t("hk_err_unsupported", key=format_hotkey(hotkey))
    mods, key = parsed
    if not mods and key in _TYPING_KEYS:
        return t("hk_err_typing")
    if not mods and key == "f12":
        return t("hk_err_f12")
    return None


def hotkey_from_vk(mods: Iterable[str], vk: int) -> Optional[str]:
    name = NAME_BY_VK.get(vk)
    return compose(mods, name) if name else None


_MODIFIER_PRESS_VK = {"ctrl": 0xA2, "shift": 0xA0, "alt": 0xA4, "windows": 0x5B}


def combo_vks(text: str) -> Optional[List[int]]:
    """Virtual keys to press for a combination, modifiers first (used by the key-hold mode)."""
    parsed = parse_hotkey(text)
    if parsed is None:
        return None
    mods, key = parsed
    return [_MODIFIER_PRESS_VK[m] for m in MODIFIER_ORDER if m in mods] + [VK_BY_NAME[key]]


def key_vk(key: Any) -> Optional[int]:
    """Virtual-key code of a pynput ``Key``/``KeyCode``."""
    value = getattr(key, "value", key)
    vk = getattr(value, "vk", None)
    return int(vk) if vk is not None else None


# ---------------------------------------------------------------------------
# Filtering the hotkeys out of a recording
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HotkeyTrigger:
    """The final (non-modifier) key of a hotkey plus the modifiers it requires."""

    modifiers: FrozenSet[str]
    names: FrozenSet[str]
    vks: FrozenSet[int] = field(default_factory=frozenset)


def trigger_for(hotkey: str) -> Optional[HotkeyTrigger]:
    parsed = parse_hotkey(hotkey)
    if parsed is None:
        return None
    mods, key = parsed
    return HotkeyTrigger(mods, frozenset({key}), frozenset({VK_BY_NAME[key]}))


# ---------------------------------------------------------------------------
# Registration (Win32) and capture (pynput)
# ---------------------------------------------------------------------------

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_APP_CALL = 0x8000 + 1
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

ERROR_IN_USE = "in_use"
ERROR_UNSUPPORTED = "unsupported"
ERROR_UNAVAILABLE = "unavailable"


class HotkeyManager:
    """Owns a thread with a Win32 message loop that receives ``WM_HOTKEY``.

    ``RegisterHotKey`` must run on the thread that pumps the messages, so all
    registration work is marshalled onto it. Callbacks run on that thread too.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._calls: queue.SimpleQueue[Tuple[Callable[[], Any], List[Any], threading.Event]] = queue.SimpleQueue()
        self._callbacks: Dict[int, Callable[[], None]] = {}
        self._next_id = 1
        self._user32: Any = None
        self._capture_listener: Any = None
        self._capture_lock = threading.Lock()

    # -- message loop --------------------------------------------------
    def _ensure_thread(self) -> bool:
        if not IS_WINDOWS:
            return False
        if self._thread is not None and self._thread.is_alive() and self._thread_id:
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="otoshi-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        return bool(self._thread_id)

    def _run(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self._user32 = user32

        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # creates this thread's message queue
        self._thread_id = kernel32.GetCurrentThreadId()
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    callback = self._callbacks.get(int(msg.wParam))
                    if callback is not None:
                        try:
                            callback()
                        except Exception:
                            logger.exception("Hotkey callback failed")
                elif msg.message == WM_APP_CALL:
                    self._drain_calls()
        finally:
            for hotkey_id in list(self._callbacks):
                user32.UnregisterHotKey(None, hotkey_id)
            self._callbacks.clear()
            self._thread_id = 0

    def _drain_calls(self) -> None:
        while True:
            try:
                fn, box, done = self._calls.get_nowait()
            except queue.Empty:
                return
            try:
                box.append((True, fn()))
            except Exception as exc:
                box.append((False, exc))
            done.set()

    def _call(self, fn: Callable[[], Any]) -> Any:
        if not self._ensure_thread():
            raise OSError("global hotkeys are only available on Windows")
        box: List[Any] = []
        done = threading.Event()
        self._calls.put((fn, box, done))
        ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_APP_CALL, 0, 0)
        if not done.wait(3.0):
            raise TimeoutError("hotkey thread did not respond")
        ok, value = box[0]
        if not ok:
            raise value
        return value

    # -- public API ----------------------------------------------------
    def bind(self, bindings: Dict[str, Tuple[str, Callable[[], None]]]) -> Dict[str, str]:
        """Replace all registrations. Returns ``{action: ERROR_*}`` for failures."""

        def work() -> Dict[str, str]:
            self._unregister_all()
            errors: Dict[str, str] = {}
            for action, (hotkey, callback) in bindings.items():
                parsed = parse_hotkey(hotkey)
                if parsed is None:
                    errors[action] = ERROR_UNSUPPORTED
                    continue
                mods, key = parsed
                flags = MOD_NOREPEAT
                for mod in mods:
                    flags |= _MOD_FLAGS[mod]
                hotkey_id = self._next_id
                self._next_id += 1
                if self._user32.RegisterHotKey(None, hotkey_id, flags, VK_BY_NAME[key]):
                    self._callbacks[hotkey_id] = callback
                else:
                    code = ctypes.get_last_error()
                    errors[action] = ERROR_IN_USE if code == ERROR_HOTKEY_ALREADY_REGISTERED else ERROR_UNAVAILABLE
                    logger.warning("RegisterHotKey(%r) failed with error %s", hotkey, code)
            return errors

        try:
            return self._call(work)
        except Exception as exc:
            logger.warning("Could not register hotkeys: %s", exc)
            return {action: ERROR_UNAVAILABLE for action in bindings}

    def _unregister_all(self) -> None:
        for hotkey_id in list(self._callbacks):
            self._user32.UnregisterHotKey(None, hotkey_id)
        self._callbacks.clear()

    def unbind_all(self) -> None:
        if self._thread_id:
            try:
                self._call(self._unregister_all)
            except Exception:
                logger.debug("unbind_all failed", exc_info=True)

    def capture(self, on_done: Callable[[Optional[str]], None]) -> None:
        """Report the next key combination (``None`` for Esc) from the listener thread.

        The combination is complete as soon as a non-modifier key goes down, so
        holding Ctrl+Shift and tapping F5 yields ``"ctrl+shift+f5"``. Keys that
        cannot be registered come back as ``"vk<code>"`` and fail validation.
        """
        from pynput import keyboard as kb

        self.cancel_capture()
        held: set = set()
        finished = threading.Event()

        def on_press(key: Any) -> Optional[bool]:
            if finished.is_set():
                return False
            vk = key_vk(key)
            if vk is None:
                return None
            modifier = _MODIFIER_VKS.get(vk)
            if modifier:
                held.add(modifier)
                return None
            finished.set()
            if vk == VK_BY_NAME["esc"] and not held:
                on_done(None)
            else:
                on_done(hotkey_from_vk(held, vk) or f"vk{vk}")
            return False

        def on_release(key: Any) -> None:
            modifier = _MODIFIER_VKS.get(key_vk(key) or -1)
            if modifier:
                held.discard(modifier)

        listener = kb.Listener(on_press=on_press, on_release=on_release)
        with self._capture_lock:
            self._capture_listener = listener
        listener.start()

    def cancel_capture(self) -> None:
        with self._capture_lock:
            listener, self._capture_listener = self._capture_listener, None
        if listener is not None:
            listener.stop()

    def shutdown(self) -> None:
        self.cancel_capture()
        self.unbind_all()
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
