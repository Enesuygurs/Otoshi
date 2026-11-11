"""User settings: typed defaults, validation, legacy migration and atomic persistence."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from . import paths
from .i18n import LANGUAGES, number, t
from .logger import logger

SCHEMA_VERSION = 2

BUTTONS = ("left", "right", "middle")
CLICK_TYPES = ("single", "double")
LOCATIONS = ("cursor", "fixed")
OVERLAY_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right")

SPEED_MIN, SPEED_MAX = 0.1, 100.0
LOOPS_MAX = 1_000_000
INTERVAL_MIN_MS, INTERVAL_MAX_MS = 1, 3_600_000
CLICKS_MAX = 10_000_000
COORD_LIMIT = 100_000
COUNTDOWN_MAX = 60
LOOP_DELAY_MAX = 3600.0
JITTER_PCT_MAX = 50
JITTER_PX_MAX = 50
HOLD_MAX_S = 86_400.0
CLICKER_ACTIONS = ("click", "hold")

DEFAULT_HOTKEYS = {"record": "f2", "play": "f3", "clicker": "f4"}


@dataclass
class Settings:
    record_hotkey: str = DEFAULT_HOTKEYS["record"]
    play_hotkey: str = DEFAULT_HOTKEYS["play"]
    clicker_hotkey: str = DEFAULT_HOTKEYS["clicker"]

    playback_speed: float = 1.0
    macro_loop_count: int = 1
    countdown_seconds: int = 3
    macro_loop_delay_s: float = 0.0
    humanize_timing_pct: int = 0
    humanize_position_px: int = 0

    ac_interval_ms: int = 1000
    ac_button: str = "left"
    ac_click_type: str = "single"
    ac_click_times: int = 0
    ac_location: str = "cursor"
    ac_x: int = 0
    ac_y: int = 0
    ac_interval_max_ms: int = 0  # 0 = fixed interval
    ac_action: str = "click"
    ac_hold_key: str = ""
    ac_hold_seconds: float = 0.0  # 0 = until stopped

    show_overlay: bool = False
    overlay_position: str = "top-left"
    close_to_tray: bool = False
    start_with_windows: bool = False
    start_in_tray: bool = False
    finish_sound: bool = True
    finish_notification: bool = False

    language: str = ""  # empty = detect from Windows on start
    last_macro_dir: str = ""
    sidebar_expanded: bool = False

    # -- hotkey helpers -------------------------------------------------
    def hotkey(self, action: str) -> str:
        return getattr(self, f"{action}_hotkey")

    def set_hotkey(self, action: str, value: str) -> None:
        setattr(self, f"{action}_hotkey", value)

    # -- (de)serialisation ---------------------------------------------
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Settings:
        data = _migrate_legacy(dict(data))
        settings = cls()
        for f in fields(cls):
            if f.name in data:
                setattr(settings, f.name, data[f.name])
        settings.normalize()
        return settings

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": SCHEMA_VERSION, **asdict(self)}

    def normalize(self) -> None:
        """Coerce every field into its valid type/range, falling back to defaults."""
        d = Settings.__new__(Settings)
        Settings.__init__(d)  # pristine defaults

        for action in DEFAULT_HOTKEYS:
            value = _as_str(self.hotkey(action), d.hotkey(action)).strip().lower()
            self.set_hotkey(action, value or d.hotkey(action))

        self.playback_speed = _as_float(self.playback_speed, d.playback_speed, SPEED_MIN, SPEED_MAX)
        self.macro_loop_count = _as_int(self.macro_loop_count, d.macro_loop_count, 0, LOOPS_MAX)
        self.countdown_seconds = _as_int(self.countdown_seconds, d.countdown_seconds, 0, COUNTDOWN_MAX)
        self.macro_loop_delay_s = _as_float(self.macro_loop_delay_s, 0.0, 0.0, LOOP_DELAY_MAX)
        self.humanize_timing_pct = _as_int(self.humanize_timing_pct, 0, 0, JITTER_PCT_MAX)
        self.humanize_position_px = _as_int(self.humanize_position_px, 0, 0, JITTER_PX_MAX)

        self.ac_interval_ms = _as_int(self.ac_interval_ms, d.ac_interval_ms, INTERVAL_MIN_MS, INTERVAL_MAX_MS)
        self.ac_button = _as_choice(self.ac_button, BUTTONS, d.ac_button)
        self.ac_click_type = _as_choice(self.ac_click_type, CLICK_TYPES, d.ac_click_type)
        self.ac_click_times = _as_int(self.ac_click_times, d.ac_click_times, 0, CLICKS_MAX)
        self.ac_location = _as_choice(self.ac_location, LOCATIONS, d.ac_location)
        self.ac_x = _as_int(self.ac_x, d.ac_x, -COORD_LIMIT, COORD_LIMIT)
        self.ac_y = _as_int(self.ac_y, d.ac_y, -COORD_LIMIT, COORD_LIMIT)
        self.ac_interval_max_ms = _as_int(self.ac_interval_max_ms, 0, 0, INTERVAL_MAX_MS)
        self.ac_action = _as_choice(self.ac_action, CLICKER_ACTIONS, d.ac_action)
        self.ac_hold_key = _as_str(self.ac_hold_key, "").strip().lower()
        self.ac_hold_seconds = _as_float(self.ac_hold_seconds, 0.0, 0.0, HOLD_MAX_S)

        self.show_overlay = _as_bool(self.show_overlay, d.show_overlay)
        self.overlay_position = _as_choice(self.overlay_position, OVERLAY_POSITIONS, d.overlay_position)
        self.close_to_tray = _as_bool(self.close_to_tray, d.close_to_tray)
        self.start_with_windows = _as_bool(self.start_with_windows, d.start_with_windows)
        self.start_in_tray = _as_bool(self.start_in_tray, d.start_in_tray)
        self.finish_sound = _as_bool(self.finish_sound, d.finish_sound)
        self.finish_notification = _as_bool(self.finish_notification, d.finish_notification)
        self.language = _as_choice(self.language, LANGUAGES, "")
        self.last_macro_dir = _as_str(self.last_macro_dir, "")
        self.sidebar_expanded = _as_bool(self.sidebar_expanded, d.sidebar_expanded)


# ---------------------------------------------------------------------------
# Loading / saving
# ---------------------------------------------------------------------------


def load_settings(path: Optional[Path] = None, legacy: Optional[Iterable[Path]] = None) -> Settings:
    """Load settings, migrating an Otoshi 1.x ``otoshi_config.json`` on first run."""
    path = path or paths.config_file()
    if path.exists():
        data = _read_json(path)
        if data is not None:
            return Settings.from_dict(data)
        backup = path.with_name(path.name + ".bad")
        try:
            os.replace(path, backup)
            logger.warning("Settings file was unreadable; moved to %s and using defaults", backup)
        except OSError:
            logger.warning("Settings file was unreadable; using defaults")
        return Settings()

    for old in legacy if legacy is not None else paths.legacy_config_files():
        if old.exists():
            data = _read_json(old)
            if data is not None:
                settings = Settings.from_dict(data)
                save_settings(settings, path)
                logger.info("Imported legacy settings from %s", old)
                return settings
    return Settings()


def save_settings(settings: Settings, path: Optional[Path] = None) -> bool:
    """Write settings atomically (temp file + replace) so a crash never truncates them."""
    path = path or paths.config_file()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        logger.exception("Failed to save settings to %s", path)
        return False


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Could not read settings from %s", path, exc_info=True)
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Legacy (1.x) migration
# ---------------------------------------------------------------------------

_LEGACY_RENAMES = {
    "ac_hotkey": "clicker_hotkey",
    "ac_type": "ac_click_type",
    "ac_loc_type": "ac_location",
    "ac_loc_x": "ac_x",
    "ac_loc_y": "ac_y",
}
_LEGACY_VALUES = {"ac_location": {"current": "cursor"}}


def _migrate_legacy(data: Dict[str, Any]) -> Dict[str, Any]:
    for old, new in _LEGACY_RENAMES.items():
        if old in data and new not in data:
            data[new] = data.pop(old)
    for key, mapping in _LEGACY_VALUES.items():
        value = data.get(key)
        if isinstance(value, str) and value.lower() in mapping:
            data[key] = mapping[value.lower()]
    return data


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _as_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    return default


def _as_int(value: Any, default: int, lo: int, hi: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default
    return max(lo, min(hi, number))


def _as_float(value: Any, default: float, lo: float, hi: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(lo, min(hi, number))


def _as_choice(value: Any, choices: Iterable[str], default: str) -> str:
    if isinstance(value, str) and value.strip().lower() in choices:
        return value.strip().lower()
    return default


# ---------------------------------------------------------------------------
# Parsers for user input (raise ValueError with a human readable message)
# ---------------------------------------------------------------------------


def int_parser(label: str, lo: int, hi: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        try:
            value = int(text.strip())
        except ValueError:
            raise ValueError(t("err_whole_number", label=label)) from None
        if not lo <= value <= hi:
            raise ValueError(t("err_range", label=label, min=number(lo), max=number(hi)))
        return value

    return parse


def parse_speed(text: str) -> float:
    cleaned = text.strip().lower().rstrip("x×").strip().replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(t("err_speed_number")) from None
    if not math.isfinite(value) or not SPEED_MIN <= value <= SPEED_MAX:
        raise ValueError(t("err_speed_range", min=f"{SPEED_MIN:g}", max=f"{SPEED_MAX:g}"))
    return round(value, 2)


def format_speed(value: float) -> str:
    return f"{value:g}x"
