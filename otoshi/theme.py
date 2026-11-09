"""Design tokens: one place for colours, type and spacing."""

from __future__ import annotations

from typing import Dict, Tuple

# Surfaces (zinc scale)
BG = "#0C0C0F"
SURFACE = "#16161A"
SURFACE_HI = "#1F1F24"
INPUT = "#1C1C21"
BORDER = "#2A2A30"
HOVER = "#2C2C33"

# Text
TEXT = "#F4F4F5"
MUTED = "#A1A1AA"
DIM = "#71717A"

# Accents: one colour per mode, used the same way everywhere
# (buttons, status pill, overlay and tray icon).
BRAND = "#F43F5E"
ROSE, ROSE_HOVER = "#F43F5E", "#E11D48"
EMERALD, EMERALD_HOVER = "#10B981", "#059669"
VIOLET, VIOLET_HOVER = "#8B5CF6", "#7C3AED"
BLUE, BLUE_HOVER = "#3B82F6", "#2563EB"
AMBER = "#F59E0B"
IDLE = "#71717A"

LEVEL_COLORS = {"info": MUTED, "success": EMERALD, "warning": AMBER, "error": ROSE}

FONT_FAMILY = "Segoe UI"
RADIUS = 10
CARD_RADIUS = 12
PAD = 18  # outer window padding

_font_cache: Dict[Tuple[int, str], object] = {}


def font(size: int = 13, weight: str = "normal"):
    """Cached ``CTkFont`` (must be called after the root window exists)."""
    import customtkinter as ctk

    key = (size, weight)
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
    return _font_cache[key]


def set_font_family(family: str) -> None:
    """Switch the UI font (CJK languages need a font with their glyphs)."""
    global FONT_FAMILY
    if family != FONT_FAMILY:
        FONT_FAMILY = family
        _font_cache.clear()
