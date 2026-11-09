"""Otoshi's icon artwork, drawn procedurally with Pillow.

Everything is described in unit coordinates (0..1) and rendered with heavy
supersampling, so the same code produces the 256 px application icon, 16 px
tray icons and the small UI glyphs. ``tools/build_icons.py`` uses
:func:`app_icon` to regenerate ``assets/icon.ico``.

Mark: a pointer cursor (the mouse) next to a record dot with click ripples,
on a dark rounded tile.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Callable, Dict, List, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import theme

Point = Tuple[float, float]
RGBA = Tuple[int, int, int, int]

# Classic pointer silhouette, tip at (0, 0); about 0.56 wide and 0.92 tall.
_ARROW: List[Point] = [
    (0.0, 0.0),
    (0.0, 0.80),
    (0.185, 0.635),
    (0.305, 0.915),
    (0.425, 0.865),
    (0.305, 0.59),
    (0.555, 0.59),
]


def _rgba(color: str, alpha: int = 255) -> RGBA:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha


def _scaled(points: Sequence[Point], scale: float, ox: float, oy: float, px: float) -> List[Point]:
    return [((ox + x * scale) * px, (oy + y * scale) * px) for x, y in points]


def _vertical_gradient(size: int, top: str, bottom: str) -> Image.Image:
    t, b = _rgba(top), _rgba(bottom)
    column = Image.new("RGBA", (1, size))
    for y in range(size):
        k = y / max(1, size - 1)
        column.putpixel((0, y), tuple(round(t[i] + (b[i] - t[i]) * k) for i in range(4)))
    return column.resize((size, size))


# ---------------------------------------------------------------------------
# Application / tray icon
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def app_icon(size: int = 256, dot: str = theme.BRAND) -> Image.Image:
    """The Otoshi mark at ``size`` px. ``dot`` recolours the record dot (tray states)."""
    small = size <= 24
    R = 1024  # working resolution
    img = Image.new("RGBA", (R, R), (0, 0, 0, 0))

    # Tile: rounded square with a soft vertical gradient.
    inset = 0.0 if small else 0.035
    box = [inset * R, inset * R, (1 - inset) * R - 1, (1 - inset) * R - 1]
    radius = (0.20 if small else 0.225) * R
    mask = Image.new("L", (R, R), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    img.paste(_vertical_gradient(R, "#2B2B33", "#0D0D11"), (0, 0), mask)

    if not small:
        rim = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle(box, radius=radius, outline=(255, 255, 255, 34), width=int(0.009 * R))
        img.alpha_composite(rim)

    # Geometry
    if small:
        arrow_scale, ax, ay = 0.66, 0.17, 0.10
        cx, cy, r = 0.705, 0.715, 0.19
    else:
        arrow_scale, ax, ay = 0.60, 0.215, 0.165
        cx, cy, r = 0.675, 0.69, 0.13

    # Glow + click ripples behind everything else.
    if not small:
        glow = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        gr = r * 1.9
        g.ellipse([(cx - gr) * R, (cy - gr) * R, (cx + gr) * R, (cy + gr) * R], fill=_rgba(dot, 70))
        glow = glow.filter(ImageFilter.GaussianBlur(0.06 * R))
        img.alpha_composite(_clip(glow, mask))

        rings = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        d = ImageDraw.Draw(rings)
        for rr, alpha in ((r + 0.065, 150), (r + 0.13, 70)):
            d.ellipse(
                [(cx - rr) * R, (cy - rr) * R, (cx + rr) * R, (cy + rr) * R],
                outline=_rgba(dot, alpha),
                width=int(0.022 * R),
            )
        img.alpha_composite(_clip(rings, mask))

    # Pointer with a soft drop shadow.
    arrow_pts = _scaled(_ARROW, arrow_scale, ax, ay, R)
    if not small:
        shadow = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        offset = 0.018 * R
        ImageDraw.Draw(shadow).polygon([(x + offset * 0.6, y + offset) for x, y in arrow_pts], fill=(0, 0, 0, 150))
        img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(0.02 * R)))
    arrow = Image.new("RGBA", (R, R), (0, 0, 0, 0))
    ad = ImageDraw.Draw(arrow)
    ad.polygon(arrow_pts, fill=_rgba("#FAFAFA"))
    ad.line(arrow_pts + [arrow_pts[0]], fill=_rgba("#FAFAFA"), width=int(0.018 * R), joint="curve")
    # Cut a gap around the dot so the two shapes never merge at small sizes.
    gap = r + (0.035 if small else 0.04)
    ad.ellipse([(cx - gap) * R, (cy - gap) * R, (cx + gap) * R, (cy + gap) * R], fill=(0, 0, 0, 0))
    img.alpha_composite(arrow)

    # Record dot.
    dot_layer = Image.new("RGBA", (R, R), (0, 0, 0, 0))
    ImageDraw.Draw(dot_layer).ellipse([(cx - r) * R, (cy - r) * R, (cx + r) * R, (cy + r) * R], fill=_rgba(dot))
    img.alpha_composite(dot_layer)

    return img.resize((size, size), Image.LANCZOS)


def _clip(layer: Image.Image, mask: Image.Image) -> Image.Image:
    """Multiply a layer's alpha by ``mask`` (keeps effects inside the tile)."""
    out = layer.copy()
    out.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return out


# ---------------------------------------------------------------------------
# UI glyphs (single colour, transparent background)
# ---------------------------------------------------------------------------


def _stroke(d: ImageDraw.ImageDraw, pts: List[Point], width: float, fill: RGBA, closed: bool = False) -> None:
    line = pts + [pts[0], pts[1]] if closed else pts
    d.line(line, fill=fill, width=max(1, int(width)), joint="curve")
    if not closed:
        for x, y in (pts[0], pts[-1]):
            d.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=fill)


def _circle(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, px: float, **kw) -> None:
    d.ellipse([(cx - r) * px, (cy - r) * px, (cx + r) * px, (cy + r) * px], **kw)


def _g_record(d, px, c):
    _circle(d, 0.5, 0.5, 0.30, px, fill=c)


def _g_stop(d, px, c):
    d.rounded_rectangle([0.25 * px, 0.25 * px, 0.75 * px, 0.75 * px], radius=0.09 * px, fill=c)


def _g_play(d, px, c):
    pts = [(0.33 * px, 0.22 * px), (0.33 * px, 0.78 * px), (0.79 * px, 0.5 * px)]
    d.polygon(pts, fill=c)
    _stroke(d, pts, 0.09 * px, c, closed=True)


def _g_save(d, px, c):
    w = 0.085 * px
    P = lambda x, y: (x * px, y * px)  # noqa: E731
    _stroke(d, [P(0.5, 0.15), P(0.5, 0.60)], w, c)
    _stroke(d, [P(0.31, 0.42), P(0.5, 0.61), P(0.69, 0.42)], w, c)
    _stroke(d, [P(0.17, 0.62), P(0.17, 0.83), P(0.83, 0.83), P(0.83, 0.62)], w, c)


def _g_open(d, px, c):
    P = lambda x, y: (x * px, y * px)  # noqa: E731
    pts = [P(0.13, 0.25), P(0.40, 0.25), P(0.49, 0.35), P(0.87, 0.35), P(0.87, 0.80), P(0.13, 0.80)]
    _stroke(d, pts, 0.085 * px, c, closed=True)


def _g_target(d, px, c):
    w = 0.08 * px
    _circle(d, 0.5, 0.5, 0.27, px, outline=c, width=int(w))
    P = lambda x, y: (x * px, y * px)  # noqa: E731
    for a, b in (
        ((0.5, 0.05), (0.5, 0.24)),
        ((0.5, 0.76), (0.5, 0.95)),
        ((0.05, 0.5), (0.24, 0.5)),
        ((0.76, 0.5), (0.95, 0.5)),
    ):
        _stroke(d, [P(*a), P(*b)], w, c)
    _circle(d, 0.5, 0.5, 0.065, px, fill=c)


def _g_cursor(d, px, c):
    pts = _scaled(_ARROW, 0.80, 0.27, 0.08, px)
    d.polygon(pts, fill=c)
    _stroke(d, pts, 0.05 * px, c, closed=True)


def _g_macro(d, px, c):
    _circle(d, 0.5, 0.5, 0.36, px, outline=c, width=int(0.085 * px))
    _circle(d, 0.5, 0.5, 0.16, px, fill=c)


def _g_gear(d, px, c):
    teeth, inner, outer, half = 8, 0.27, 0.45, 0.085
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        ca, sa = math.cos(a), math.sin(a)
        corners = []
        for r, s in ((inner, -half), (outer, -half), (outer, half), (inner, half)):
            corners.append(((0.5 + r * ca - s * sa) * px, (0.5 + r * sa + s * ca) * px))
        d.polygon(corners, fill=c)
        _stroke(d, corners, 0.03 * px, c, closed=True)
    _circle(d, 0.5, 0.5, 0.325, px, fill=c)
    _circle(d, 0.5, 0.5, 0.13, px, fill=(0, 0, 0, 0))


def _g_folder(d, px, c):
    _g_open(d, px, c)


_GLYPHS: Dict[str, Callable] = {
    "record": _g_record,
    "stop": _g_stop,
    "play": _g_play,
    "save": _g_save,
    "open": _g_open,
    "target": _g_target,
    "cursor": _g_cursor,
    "macro": _g_macro,
    "gear": _g_gear,
    "folder": _g_folder,
}


@lru_cache(maxsize=128)
def glyph(name: str, color: str, size: int) -> Image.Image:
    px = size * 8
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    _GLYPHS[name](ImageDraw.Draw(img), px, _rgba(color))
    return img.resize((size, size), Image.LANCZOS)


_ctk_cache: Dict[Tuple[str, str, int], object] = {}


def ctk_glyph(name: str, color: str, size: int = 18):
    """A ``CTkImage`` for buttons/labels, rendered at 3x for high-DPI screens."""
    import customtkinter as ctk

    key = (name, color, size)
    if key not in _ctk_cache:
        img = glyph(name, color, size * 3)
        _ctk_cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _ctk_cache[key]


def ctk_logo(size: int = 26):
    import customtkinter as ctk

    key = ("logo", "", size)
    if key not in _ctk_cache:
        img = app_icon(size * 3)
        _ctk_cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _ctk_cache[key]
