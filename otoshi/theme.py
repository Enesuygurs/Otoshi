"""Design tokens and the Qt style sheet built from them."""

from __future__ import annotations

# Surfaces (zinc scale)
BG = "#0C0C0F"
SIDEBAR = "#111114"
SURFACE = "#17171B"
SURFACE_HI = "#202026"
INPUT = "#1D1D22"
BORDER = "#2A2A31"
HOVER = "#2A2A31"

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
AMBER, AMBER_HOVER = "#F59E0B", "#D97706"
IDLE = "#71717A"

# Pre-rendered app/tray icon variants (assets/app-<name>.png), keyed by dot colour.
ICON_VARIANTS = {"brand": BRAND, "idle": IDLE, "emerald": EMERALD, "violet": VIOLET, "amber": AMBER}

LEVEL_COLORS = {"info": MUTED, "success": EMERALD, "warning": AMBER, "error": ROSE}

FONT_FAMILY = "Segoe UI"


def set_font_family(family: str) -> None:
    global FONT_FAMILY
    FONT_FAMILY = family


def stylesheet(chevron_path: str) -> str:
    chevron = chevron_path.replace("\\", "/")
    return f"""
* {{ font-family: "{FONT_FAMILY}"; font-size: 10pt; color: {TEXT}; outline: 0; }}
QMainWindow, #Content {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 8px;
    border-radius: 6px; }}

#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#Brand {{ font-size: 14pt; font-weight: 700; }}
#NavButton {{
    text-align: left; padding: 0 12px; border: none; border-radius: 8px;
    color: {MUTED}; font-weight: 600; background: transparent;
}}
#NavButton:hover {{ background: {SURFACE}; color: {TEXT}; }}
#NavButton:checked {{ background: {SURFACE_HI}; color: {TEXT}; }}
#Version {{ color: {DIM}; font-size: 8.5pt; }}

#Pill {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
#PillText {{ font-weight: 600; font-size: 9pt; }}

#PageTitle {{ font-size: 17pt; font-weight: 700; }}
#PageSubtitle {{ color: {MUTED}; }}
#SectionTitle {{ color: {MUTED}; font-size: 9pt; font-weight: 700; padding-left: 2px; }}
#SectionDesc {{ color: {DIM}; font-size: 9pt; padding-left: 2px; }}

#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
#Separator {{ background: {BORDER}; border: none; }}
#RowTitle {{ font-weight: 500; }}
#RowDesc {{ color: {DIM}; font-size: 9pt; }}
#Info {{ color: {MUTED}; }}
#Toast {{ color: {DIM}; font-size: 9pt; }}

QPushButton {{ border-radius: 8px; padding: 0 14px; font-weight: 600; }}
QPushButton:disabled {{ color: {DIM}; }}
#Primary {{ border: none; color: white; font-size: 10.5pt; }}
#Primary[variant="rose"] {{ background: {ROSE}; }}
#Primary[variant="rose"]:hover {{ background: {ROSE_HOVER}; }}
#Primary[variant="emerald"] {{ background: {EMERALD}; }}
#Primary[variant="emerald"]:hover {{ background: {EMERALD_HOVER}; }}
#Primary[variant="violet"] {{ background: {VIOLET}; }}
#Primary[variant="violet"]:hover {{ background: {VIOLET_HOVER}; }}
#Primary[variant="amber"] {{ background: {AMBER}; }}
#Primary[variant="amber"]:hover {{ background: {AMBER_HOVER}; }}
#Primary:disabled {{ background: {SURFACE_HI}; color: {DIM}; }}
#Secondary, #Kbd {{ background: {SURFACE_HI}; border: 1px solid {BORDER}; }}
#Secondary:hover, #Kbd:hover {{ background: {HOVER}; border-color: #3A3A42; }}
#Secondary:pressed, #Kbd:pressed {{ background: {INPUT}; }}
#Kbd {{ font-family: "Cascadia Mono", "Consolas", "{FONT_FAMILY}"; font-size: 9.5pt; min-width: 120px; }}
#Kbd[capturing="true"] {{ border-color: {ROSE}; color: {ROSE}; }}
#Kbd:disabled {{ background: {INPUT}; }}

#Segment {{ background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; }}
#SegmentButton {{ border: none; border-radius: 6px; padding: 0 12px; color: {MUTED}; background: transparent; }}
#SegmentButton:hover {{ color: {TEXT}; }}
#SegmentButton:checked {{ background: {VIOLET}; color: white; }}

QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 0 10px; min-height: 30px; selection-background-color: {BLUE};
}}
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: #3A3A42; }}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {BLUE}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {DIM}; background: {SURFACE}; }}
QComboBox {{ padding-right: 28px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 0; height: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_HI}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
    selection-background-color: {HOVER}; selection-color: {TEXT};
}}
QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 0 8px; border-radius: 6px; }}

QScrollArea, #qt_scrollarea_viewport, #PageBody {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3A3A42; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page,
QScrollBar::sub-page {{ height: 0; background: none; }}

QMenu {{ background: {SURFACE_HI}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
"""
