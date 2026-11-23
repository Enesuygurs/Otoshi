"""Design tokens and the Qt style sheet built from them.

The look is borderless: structure comes from surface tones, rounded tiles and
spacing instead of outlines and divider lines. Surfaces get lighter the
further "up" they sit: sidebar < window < tile < control < hover.
"""

from __future__ import annotations

# Surfaces (cool zinc scale, darkest to lightest)
SIDEBAR = "#09090B"
BG = "#0E0E11"
SURFACE = "#1A1A1F"
SURFACE_HI = "#232329"
INPUT = "#232329"
HOVER = "#2C2C33"
HOVER_HI = "#34343C"
PRESSED = "#1E1E23"
FOCUS = "#252B3B"  # input fill while it has keyboard focus (a soft blue tint)
BORDER = "#2A2A31"  # only for floating surfaces (menus, tooltips, overlay) over arbitrary backgrounds

# Text
TEXT = "#F4F4F5"
MUTED = "#A1A1AA"
DIM = "#71717A"

# Accents: one colour per mode, used the same way everywhere
# (buttons, status pill, overlay and tray icon). Hover lifts, pressed sinks.
BRAND = "#F43F5E"
ROSE, ROSE_HOVER, ROSE_PRESSED = "#F43F5E", "#F6566F", "#E11D48"
EMERALD, EMERALD_HOVER, EMERALD_PRESSED = "#10B981", "#1EC590", "#059669"
VIOLET, VIOLET_HOVER, VIOLET_PRESSED = "#8B5CF6", "#996FF8", "#7C3AED"
BLUE, BLUE_HOVER = "#3B82F6", "#2563EB"
AMBER, AMBER_HOVER, AMBER_PRESSED = "#F59E0B", "#F7AA2C", "#D97706"
IDLE = "#71717A"

# Pre-rendered app/tray icon variants (assets/app-<name>.png), keyed by dot colour.
ICON_VARIANTS = {"brand": BRAND, "idle": IDLE, "emerald": EMERALD, "violet": VIOLET, "amber": AMBER}

# Corner radii. Rows of a card are separate tiles that read as one rounded
# block: large outer corners, small inner corners.
RADIUS_TILE, RADIUS_TILE_INNER, RADIUS_CONTROL = 12, 4, 8


def tint(color: str, alpha: float) -> str:
    """``rgba()`` of a ``#RRGGBB`` colour, for soft accent-tinted fills."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


FONT_FAMILY = "Segoe UI"


def set_font_family(family: str) -> None:
    global FONT_FAMILY
    FONT_FAMILY = family


def _primary(variant: str, base: str, hover: str, pressed: str) -> str:
    sel = f'#Primary[variant="{variant}"]'
    return f"{sel} {{ background: {base}; }}\n{sel}:hover {{ background: {hover}; }}\n" + (
        f"{sel}:pressed {{ background: {pressed}; }}"
    )


def stylesheet(chevron_path: str) -> str:
    chevron = chevron_path.replace("\\", "/")
    rt, ri, rc = RADIUS_TILE, RADIUS_TILE_INNER, RADIUS_CONTROL
    primaries = "\n".join(
        _primary(*args)
        for args in (
            ("rose", ROSE, ROSE_HOVER, ROSE_PRESSED),
            ("emerald", EMERALD, EMERALD_HOVER, EMERALD_PRESSED),
            ("violet", VIOLET, VIOLET_HOVER, VIOLET_PRESSED),
            ("amber", AMBER, AMBER_HOVER, AMBER_PRESSED),
        )
    )
    return f"""
* {{ font-family: "{FONT_FAMILY}"; font-size: 9pt; color: {TEXT}; outline: 0; }}
QMainWindow, #Content {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 5px 9px;
    border-radius: 8px; }}

#Sidebar {{ background: {SIDEBAR}; border: none; }}
#Brand {{ font-size: 13pt; font-weight: 700; }}
#NavButton {{
    text-align: left; padding: 0 0 0 11px; border: none; border-radius: 10px;
    color: {MUTED}; font-weight: 600; background: transparent;
}}
#NavButton:hover {{ background: {SURFACE}; color: {TEXT}; }}
#NavButton:pressed {{ background: {PRESSED}; }}
#NavButton:checked {{ background: {SURFACE_HI}; color: {TEXT}; }}
#Version {{ color: {DIM}; font-size: 8.5pt; }}

#Pill {{ background: {SURFACE}; border: none; border-radius: 12px; }}
#PillText {{ font-weight: 600; font-size: 8.5pt; }}

#PageTitle {{ font-size: 14pt; font-weight: 700; }}
#PageSubtitle {{ color: {MUTED}; }}
#SectionTitle {{ color: {MUTED}; font-size: 8pt; font-weight: 700; }}
#SectionDesc {{ color: {DIM}; font-size: 8pt; }}

#Card {{ background: transparent; border: none; }}
#Tile {{ background: {SURFACE}; border: none; border-radius: {ri}px; }}
#Tile[pos="first"] {{ border-top-left-radius: {rt}px; border-top-right-radius: {rt}px; }}
#Tile[pos="last"] {{ border-bottom-left-radius: {rt}px; border-bottom-right-radius: {rt}px; }}
#Tile[pos="only"] {{ border-radius: {rt}px; }}
#RowTitle {{ font-weight: 500; }}
#RowDesc {{ color: {DIM}; font-size: 8pt; }}
#Info {{ color: {MUTED}; }}
#MacroPanel {{ background: {SURFACE_HI}; border: none; border-radius: 10px; }}
#MacroTitle {{ font-weight: 600; }}
#MacroMeta {{ color: {MUTED}; font-size: 8pt; }}

QPushButton {{ border: none; border-radius: {rc}px; padding: 0 10px; font-weight: 600; }}
QPushButton:disabled {{ color: {DIM}; }}
#Primary {{ border: none; border-radius: 10px; color: white; font-size: 9.5pt; }}
{primaries}
#Primary:disabled {{ background: {SURFACE_HI}; color: {DIM}; }}
#Secondary, #Kbd {{ background: {SURFACE_HI}; border: none; }}
#MacroPanel #Secondary {{ background: {HOVER}; }}
#Secondary:hover, #Kbd:hover, #MacroPanel #Secondary:hover {{ background: {HOVER_HI}; }}
#Secondary:pressed, #Kbd:pressed, #MacroPanel #Secondary:pressed {{ background: {PRESSED}; }}
#Secondary:disabled, #Kbd:disabled, #MacroPanel #Secondary:disabled {{ background: {PRESSED}; }}
#Kbd {{ font-family: "Cascadia Mono", "Consolas", "{FONT_FAMILY}"; font-size: 8.5pt; color: {MUTED};
    min-width: 100px; min-height: 28px; }}
#Kbd:hover {{ color: {TEXT}; }}
#Kbd[capturing="true"] {{ background: {tint(ROSE, 0.16)}; color: {ROSE_HOVER}; }}

#Segment {{ background: {SURFACE_HI}; border: none; border-radius: 10px; }}
#SegmentButton {{ border: none; border-radius: 7px; padding: 0 12px 2px 12px; color: {MUTED};
    background: transparent; }}
#SegmentButton:hover {{ color: {TEXT}; background: {HOVER}; }}
#SegmentButton:checked {{ background: {VIOLET}; color: white; }}

QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {INPUT}; border: none; border-radius: {rc}px;
    padding: 0 8px; min-height: 28px; selection-background-color: {BLUE};
}}
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QComboBox:on {{ background: {HOVER}; }}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ background: {FOCUS}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {DIM}; background: {SURFACE_HI}; }}
/* Spin boxes: no side padding, so centred text is really centred (the hidden
   arrow buttons would otherwise keep a strip on the right). The 2 px bottom
   padding in both lifts Segoe UI text to the optical centre. */
QSpinBox, QDoubleSpinBox {{ padding: 0 0 2px 0; min-height: 26px; }}
QComboBox {{ padding: 0 28px 2px 10px; min-height: 26px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 0; height: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_HI}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px;
    selection-background-color: {HOVER}; selection-color: {TEXT};
}}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 0 8px; border-radius: 6px; }}

QScrollArea, #qt_scrollarea_viewport, #PageBody {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {HOVER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {HOVER_HI}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page,
QScrollBar::sub-page {{ height: 0; background: none; }}

QMenu {{ background: {SURFACE_HI}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::separator {{ height: 1px; background: {HOVER}; margin: 4px 6px; }}
"""
