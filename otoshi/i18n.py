"""Translations. Strings live in ``otoshi/locales/<code>.json``; English is the fallback."""

from __future__ import annotations

import json
import locale
import os
from functools import cache
from pathlib import Path
from typing import Any, Dict, Optional

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
DEFAULT = "en"

# Native names, in the order shown in the language menu.
LANGUAGES: Dict[str, str] = {
    "en": "English",
    "tr": "Türkçe",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
    "ja": "日本語",
    "zh": "简体中文",
}

# Segoe UI has no CJK glyphs; these fonts ship with Windows 10/11.
_FONT_FAMILIES = {"ja": "Yu Gothic UI", "zh": "Microsoft YaHei UI"}
_THOUSANDS = {"tr": ".", "de": ".", "es": ".", "it": ".", "pt": ".", "fr": " ", "ru": " "}

_current = DEFAULT


@cache
def table(code: str) -> Dict[str, str]:
    try:
        return json.loads((LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_language(code: Optional[str]) -> str:
    global _current
    _current = code if code in LANGUAGES else DEFAULT
    return _current


def language() -> str:
    return _current


def t(key: str, /, **kwargs: Any) -> str:
    """Translated string for ``key`` formatted with ``kwargs`` (falls back to English, then the key)."""
    text = table(_current).get(key) or table(DEFAULT).get(key) or key
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


def number(value: int) -> str:
    """Integer with the language's thousands separator (1,234 / 1.234 / 1 234)."""
    return f"{value:,}".replace(",", _THOUSANDS.get(_current, ","))


def upper(text: str) -> str:
    """Locale-aware upper case (Turkish dotted/dotless i)."""
    if _current == "tr":
        text = text.replace("i", "İ")
    return text.upper()


def font_family(code: Optional[str] = None) -> str:
    return _FONT_FAMILIES.get(code or _current, "Segoe UI")


def detect_system_language() -> str:
    """Best supported match for the Windows UI language (or the POSIX locale)."""
    candidates = []
    if os.name == "nt":
        try:
            import ctypes

            candidates.append(locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage()))
        except Exception:
            pass
    candidates.extend(os.environ.get(var) for var in ("LC_ALL", "LC_MESSAGES", "LANG"))
    for name in candidates:
        if name:
            code = name.replace("-", "_").split("_")[0].lower()
            if code in LANGUAGES:
                return code
    return DEFAULT
