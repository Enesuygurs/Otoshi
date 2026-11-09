"""Macro recording, playback and file format.

Events are plain JSON-compatible dicts, so the in-memory form is exactly what
gets written to ``.otm`` files::

    {"t": 0.42, "type": "move",   "x": 10, "y": 20}
    {"t": 0.50, "type": "click",  "x": 10, "y": 20, "button": "left", "pressed": true}
    {"t": 0.61, "type": "scroll", "x": 10, "y": 20, "dx": 0, "dy": -1}
    {"t": 0.70, "type": "key",    "key": {"vk": 65, "char": "a"}, "pressed": true}
    {"t": 0.71, "type": "key",    "key": {"name": "shift"},       "pressed": false}

``t`` is seconds since the recording started.
"""

from __future__ import annotations

import io
import json
import math
import os
import pickle
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from pynput import keyboard as kb
from pynput import mouse as ms

from . import __version__
from .i18n import t
from .logger import logger
from .timing import sleep_until

if TYPE_CHECKING:
    from .hotkeys import HotkeyTrigger

Event = Dict[str, Any]
Rect = Tuple[int, int, int, int]

FILE_FORMAT = "otoshi-macro"
FILE_VERSION = 2
MAX_FILE_BYTES = 64 * 1024 * 1024
_MIN_LOOP_SECONDS = 0.01  # keeps a zero-length infinite loop from pinning a CPU core

_PYNPUT_MODIFIERS = {
    "ctrl": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift": "shift",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "cmd": "windows",
    "cmd_l": "windows",
    "cmd_r": "windows",
}


class MacroFileError(Exception):
    """Raised with a user-facing message when a macro file cannot be used."""


# ---------------------------------------------------------------------------
# Key / button conversion
# ---------------------------------------------------------------------------


def key_to_spec(key: Any) -> Optional[Dict[str, Any]]:
    if isinstance(key, kb.Key):
        return {"name": key.name}
    if isinstance(key, kb.KeyCode):
        spec: Dict[str, Any] = {}
        if key.vk is not None:
            spec["vk"] = int(key.vk)
        if key.char is not None:
            spec["char"] = key.char
        return spec or None
    return None


def spec_to_key(spec: Dict[str, Any]) -> Any:
    name = spec.get("name")
    if name is not None:
        try:
            return kb.Key[name]
        except KeyError:
            return None
    vk, char = spec.get("vk"), spec.get("char")
    if vk is None and char is None:
        return None
    return kb.KeyCode(vk=vk, char=char)


def _key_identity(spec: Dict[str, Any]) -> str:
    if "name" in spec:
        return f"n:{spec['name']}"
    if spec.get("vk") is not None:
        return f"v:{spec['vk']}"
    return f"c:{spec.get('char')}"


def _input_identity(event: Event) -> Optional[str]:
    if event["type"] == "click":
        return f"b:{event['button']}"
    if event["type"] == "key":
        return f"k:{_key_identity(event['key'])}"
    return None


def _pynput_key_name(key: Any) -> Optional[str]:
    if isinstance(key, kb.Key):
        return key.name
    if isinstance(key, kb.KeyCode) and key.char:
        return key.char.lower()
    return None


def _pynput_key_vk(key: Any) -> Optional[int]:
    if isinstance(key, kb.Key):
        return getattr(key.value, "vk", None)
    if isinstance(key, kb.KeyCode):
        return key.vk
    return None


# ---------------------------------------------------------------------------
# Cleaning up a raw recording
# ---------------------------------------------------------------------------


def sanitize_events(events: Sequence[Event], exclude_rect: Optional[Rect] = None) -> List[Event]:
    """Make a raw recording safe to replay.

    * Trailing clicks inside ``exclude_rect`` (Otoshi's own window, i.e. the
      click on "Stop") are removed together with the moves that follow them.
    * Releases without a press (the click that started the recording) and
      presses that are never released (a modifier still held when the stop
      hotkey fired) are dropped, so playback never leaves a key held down.
    """
    result = list(events)
    if exclude_rect is not None:
        result = _trim_trailing_self_clicks(result, exclude_rect)
    return _drop_unmatched(result)


def _trim_trailing_self_clicks(events: List[Event], rect: Rect) -> List[Event]:
    left, top, right, bottom = rect
    cut = len(events)
    i = len(events) - 1
    while i >= 0:
        ev = events[i]
        if ev["type"] == "move":
            i -= 1
            continue
        if ev["type"] == "click" and left <= ev["x"] < right and top <= ev["y"] < bottom:
            cut = i
            i -= 1
            continue
        break
    return events[:cut]


def _drop_unmatched(events: List[Event]) -> List[Event]:
    keep = [True] * len(events)
    open_presses: Dict[str, List[int]] = {}
    for index, ev in enumerate(events):
        ident = _input_identity(ev)
        if ident is None:
            continue
        if ev["pressed"]:
            open_presses.setdefault(ident, []).append(index)  # auto-repeat adds more
        elif open_presses.get(ident):
            open_presses[ident] = []
        else:
            keep[index] = False
    for indexes in open_presses.values():
        for index in indexes:
            keep[index] = False
    return [ev for ev, k in zip(events, keep) if k]


def macro_duration(events: Sequence[Event]) -> float:
    return float(events[-1]["t"]) if events else 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MacroEngine:
    """Records input with pynput listeners and replays it on a worker thread.

    The engine never touches the UI. Completion is reported through the
    ``on_finish`` callback, which runs on the worker thread.
    """

    def __init__(self) -> None:
        self.events: List[Event] = []
        self._mouse = ms.Controller()
        self._keyboard = kb.Controller()

        self._buffer: List[Event] = []
        self._t0 = 0.0
        self._mouse_listener: Optional[ms.Listener] = None
        self._key_listener: Optional[kb.Listener] = None
        self._triggers: Sequence[HotkeyTrigger] = ()
        self._held_modifiers: Set[str] = set()
        self._swallowed: Set[Any] = set()

        self._play_thread: Optional[threading.Thread] = None
        self._play_stop = threading.Event()
        self.current_loop = 0

    # -- state ---------------------------------------------------------
    @property
    def is_recording(self) -> bool:
        return self._mouse_listener is not None

    @property
    def is_playing(self) -> bool:
        thread = self._play_thread
        return thread is not None and thread.is_alive() and not self._play_stop.is_set()

    @property
    def duration(self) -> float:
        return macro_duration(self.events)

    @property
    def recorded_so_far(self) -> int:
        return len(self._buffer)

    @property
    def recording_elapsed(self) -> float:
        return time.perf_counter() - self._t0 if self.is_recording else 0.0

    # -- recording -----------------------------------------------------
    def start_recording(self, triggers: Iterable[HotkeyTrigger] = ()) -> bool:
        if self.is_recording or self.is_playing:
            return False
        self._buffer = []
        self._triggers = tuple(triggers)
        self._held_modifiers = set()
        self._swallowed = set()
        self._t0 = time.perf_counter()
        self._mouse_listener = ms.Listener(on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll)
        self._key_listener = kb.Listener(
            on_press=lambda k: self._on_key(k, True), on_release=lambda k: self._on_key(k, False)
        )
        self._mouse_listener.start()
        self._key_listener.start()
        return True

    def stop_recording(self, exclude_rect: Optional[Rect] = None) -> int:
        """Stop listening. Returns the number of usable events captured.

        An empty recording keeps the previous macro instead of wiping it.
        """
        if not self.is_recording:
            return 0
        for listener in (self._mouse_listener, self._key_listener):
            if listener is not None:
                listener.stop()
        self._mouse_listener = self._key_listener = None
        events = sanitize_events(self._buffer, exclude_rect)
        self._buffer = []
        if events:
            self.events = events
        return len(events)

    def _now(self) -> float:
        return round(time.perf_counter() - self._t0, 4)

    def _on_move(self, x: int, y: int) -> None:
        self._buffer.append({"t": self._now(), "type": "move", "x": int(x), "y": int(y)})

    def _on_click(self, x: int, y: int, button: ms.Button, pressed: bool) -> None:
        name = getattr(button, "name", None)
        if name and name != "unknown":
            self._buffer.append(
                {"t": self._now(), "type": "click", "x": int(x), "y": int(y), "button": name, "pressed": bool(pressed)}
            )

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._buffer.append(
            {"t": self._now(), "type": "scroll", "x": int(x), "y": int(y), "dx": int(dx), "dy": int(dy)}
        )

    def _on_key(self, key: Any, pressed: bool) -> None:
        name = _pynput_key_name(key)
        modifier = _PYNPUT_MODIFIERS.get(name or "")
        if modifier:
            (self._held_modifiers.add if pressed else self._held_modifiers.discard)(modifier)
        else:
            vk = _pynput_key_vk(key)
            ident = vk if vk is not None else name
            if pressed and self._is_hotkey(name, vk):
                self._swallowed.add(ident)
                return
            if not pressed and ident in self._swallowed:
                self._swallowed.discard(ident)
                return
        spec = key_to_spec(key)
        if spec:
            self._buffer.append({"t": self._now(), "type": "key", "key": spec, "pressed": bool(pressed)})

    def _is_hotkey(self, name: Optional[str], vk: Optional[int]) -> bool:
        readable = name.replace("_", " ") if name else None
        for trigger in self._triggers:
            if trigger.modifiers != self._held_modifiers:
                continue
            if (vk is not None and vk in trigger.vks) or (readable is not None and readable in trigger.names):
                return True
        return False

    # -- playback ------------------------------------------------------
    def play(self, loops: int, speed: float, on_finish: Optional[Callable[[], None]] = None) -> bool:
        """Replay ``self.events`` ``loops`` times (0 = until stopped)."""
        if self.is_recording or self.is_playing or not self.events:
            return False
        self._join_previous()
        speed = speed if speed > 0 else 1.0
        actions = _compile(self.events)
        self._play_stop = threading.Event()
        self.current_loop = 0
        self._play_thread = threading.Thread(
            target=self._play_worker,
            args=(actions, max(0, loops), speed, self._play_stop, on_finish),
            name="otoshi-playback",
            daemon=True,
        )
        self._play_thread.start()
        return True

    def stop_playback(self) -> None:
        self._play_stop.set()

    def _join_previous(self) -> None:
        thread = self._play_thread
        if thread is not None and thread.is_alive():
            self._play_stop.set()
            thread.join(timeout=1.0)

    def _play_worker(
        self,
        actions: List[Tuple[float, str, tuple]],
        loops: int,
        speed: float,
        stop: threading.Event,
        on_finish: Optional[Callable[[], None]],
    ) -> None:
        held_keys: Dict[str, Any] = {}
        held_buttons: Dict[str, ms.Button] = {}
        try:
            loop = 0
            while not stop.is_set() and (loops == 0 or loop < loops):
                loop += 1
                self.current_loop = loop
                start = time.perf_counter()
                for t, kind, args in actions:
                    if sleep_until(start + t / speed, stop):
                        break
                    self._apply(kind, args, held_keys, held_buttons)
                self._release_all(held_keys, held_buttons)
                if time.perf_counter() - start < _MIN_LOOP_SECONDS:
                    stop.wait(_MIN_LOOP_SECONDS)
        except Exception:
            logger.exception("Macro playback failed")
        finally:
            self._release_all(held_keys, held_buttons)
            if on_finish is not None:
                on_finish()

    def _apply(self, kind: str, args: tuple, held_keys: Dict[str, Any], held_buttons: Dict[str, ms.Button]) -> None:
        try:
            if kind == "move":
                self._mouse.position = args
            elif kind == "click":
                x, y, button, name, pressed = args
                self._mouse.position = (x, y)
                if pressed:
                    self._mouse.press(button)
                    held_buttons[name] = button
                else:
                    self._mouse.release(button)
                    held_buttons.pop(name, None)
            elif kind == "scroll":
                x, y, dx, dy = args
                self._mouse.position = (x, y)
                self._mouse.scroll(dx, dy)
            elif kind == "key":
                key, ident, pressed = args
                if pressed:
                    self._keyboard.press(key)
                    held_keys[ident] = key
                else:
                    self._keyboard.release(key)
                    held_keys.pop(ident, None)
        except Exception:
            logger.debug("Skipped event %s %r", kind, args, exc_info=True)

    def _release_all(self, held_keys: Dict[str, Any], held_buttons: Dict[str, ms.Button]) -> None:
        for key in list(held_keys.values()):
            try:
                self._keyboard.release(key)
            except Exception:
                pass
        for button in list(held_buttons.values()):
            try:
                self._mouse.release(button)
            except Exception:
                pass
        held_keys.clear()
        held_buttons.clear()

    def shutdown(self) -> None:
        if self.is_recording:
            self.stop_recording()
        self.stop_playback()
        self._join_previous()


def _compile(events: Sequence[Event]) -> List[Tuple[float, str, tuple]]:
    """Resolve buttons/keys once so the timing loop only does the input calls."""
    actions: List[Tuple[float, str, tuple]] = []
    for ev in events:
        kind, t = ev["type"], float(ev["t"])
        if kind == "move":
            actions.append((t, "move", (ev["x"], ev["y"])))
        elif kind == "click":
            button = getattr(ms.Button, ev["button"], None)
            if button is not None:
                actions.append((t, "click", (ev["x"], ev["y"], button, ev["button"], ev["pressed"])))
        elif kind == "scroll":
            actions.append((t, "scroll", (ev["x"], ev["y"], ev["dx"], ev["dy"])))
        elif kind == "key":
            key = spec_to_key(ev["key"])
            if key is not None:
                actions.append((t, "key", (key, _key_identity(ev["key"]), ev["pressed"])))
    return actions


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


@dataclass
class LoadedMacro:
    events: List[Event]
    loop_count: Optional[int]
    speed: Optional[float]
    legacy: bool = False


def save_macro(path: Path, events: Sequence[Event], loop_count: int, speed: float) -> None:
    payload = {
        "format": FILE_FORMAT,
        "version": FILE_VERSION,
        "app_version": __version__,
        "loop_count": int(loop_count),
        "speed": float(speed),
        "events": list(events),
    }
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise MacroFileError(t("mf_write", error=exc.strerror or exc)) from exc


def load_macro(path: Path) -> LoadedMacro:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise MacroFileError(t("mf_too_large"))
        raw = path.read_bytes()
    except OSError as exc:
        raise MacroFileError(t("mf_read", error=exc.strerror or exc)) from exc

    if raw[:1] == b"\x80":  # pickle protocol 2+ -> Otoshi 1.x file
        return _load_legacy(raw)

    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise MacroFileError(t("mf_not_macro")) from None
    if not isinstance(data, dict) or data.get("format") != FILE_FORMAT:
        raise MacroFileError(t("mf_not_macro"))
    if int(data.get("version", 0) or 0) > FILE_VERSION:
        raise MacroFileError(t("mf_newer"))

    events = _validated_events(data.get("events"))
    return LoadedMacro(events, _opt_int(data.get("loop_count")), _opt_float(data.get("speed")))


def _validated_events(raw_events: Any) -> List[Event]:
    if not isinstance(raw_events, list):
        raise MacroFileError(t("mf_damaged"))
    events = [ev for ev in (_validate_event(e) for e in raw_events) if ev is not None]
    if not events:
        raise MacroFileError(t("mf_empty"))
    events.sort(key=lambda e: e["t"])
    return events


def _num(value: Any, cast: Callable[[Any], Any]) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError
    return cast(value)


def _validate_event(ev: Any) -> Optional[Event]:
    if not isinstance(ev, dict):
        return None
    try:
        t = _num(ev["t"], float)
        if t < 0:
            return None
        kind = ev["type"]
        if kind == "move":
            return {"t": t, "type": "move", "x": _num(ev["x"], int), "y": _num(ev["y"], int)}
        if kind == "click":
            button = ev["button"]
            if not isinstance(button, str) or not isinstance(ev["pressed"], bool):
                return None
            return {
                "t": t,
                "type": "click",
                "x": _num(ev["x"], int),
                "y": _num(ev["y"], int),
                "button": button,
                "pressed": ev["pressed"],
            }
        if kind == "scroll":
            return {
                "t": t,
                "type": "scroll",
                "x": _num(ev["x"], int),
                "y": _num(ev["y"], int),
                "dx": _num(ev["dx"], int),
                "dy": _num(ev["dy"], int),
            }
        if kind == "key":
            spec = ev["key"]
            if not isinstance(spec, dict) or not isinstance(ev["pressed"], bool):
                return None
            clean: Dict[str, Any] = {}
            if isinstance(spec.get("name"), str):
                clean["name"] = spec["name"]
            else:
                if spec.get("vk") is not None:
                    clean["vk"] = _num(spec["vk"], int)
                if isinstance(spec.get("char"), str):
                    clean["char"] = spec["char"]
            if not clean:
                return None
            return {"t": t, "type": "key", "key": clean, "pressed": ev["pressed"]}
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _opt_int(value: Any) -> Optional[int]:
    try:
        return int(_num(value, int))
    except ValueError:
        return None


def _opt_float(value: Any) -> Optional[float]:
    try:
        return float(_num(value, float))
    except ValueError:
        return None


class _LegacyUnpickler(pickle.Unpickler):
    """Only lets the pynput Key/KeyCode/Button classes through.

    Otoshi 1.x stored macros with plain ``pickle``, which can execute arbitrary
    code when a crafted file is opened. Anything outside this allow-list is
    rejected before it can be imported or called.
    """

    def find_class(self, module: str, name: str) -> Any:
        if module.startswith("pynput.keyboard.") and name in ("Key", "KeyCode"):
            return super().find_class(module, name)
        if module.startswith("pynput.mouse.") and name == "Button":
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"forbidden global {module}.{name}")


def _load_legacy(raw: bytes) -> LoadedMacro:
    try:
        payload = _LegacyUnpickler(io.BytesIO(raw)).load()
    except Exception as exc:
        logger.warning("Rejected legacy macro file: %s", exc)
        raise MacroFileError(t("mf_legacy_unsafe")) from None

    if isinstance(payload, dict) and "events" in payload:
        raw_events, loop_count = payload.get("events"), _opt_int(payload.get("loop_count"))
    else:
        raw_events, loop_count = payload, None
    if not isinstance(raw_events, list):
        raise MacroFileError(t("mf_damaged"))

    converted = [c for c in (_convert_legacy_event(e) for e in raw_events) if c is not None]
    return LoadedMacro(_validated_events(converted), loop_count, None, legacy=True)


def _convert_legacy_event(ev: Any) -> Optional[Event]:
    if not isinstance(ev, dict):
        return None
    try:
        t, kind = ev["time"], ev["type"]
        if kind in ("move", "click", "scroll"):
            x, y = ev["pos"]
        if kind == "move":
            return {"t": t, "type": "move", "x": x, "y": y}
        if kind == "click":
            return {
                "t": t,
                "type": "click",
                "x": x,
                "y": y,
                "button": getattr(ev["button"], "name", None),
                "pressed": bool(ev["pressed"]),
            }
        if kind == "scroll":
            return {"t": t, "type": "scroll", "x": x, "y": y, "dx": ev["dx"], "dy": ev["dy"]}
        if kind in ("keypress", "keyrelease"):
            spec = key_to_spec(ev["key"])
            return {"t": t, "type": "key", "key": spec, "pressed": kind == "keypress"} if spec else None
    except (KeyError, TypeError, ValueError):
        return None
    return None
