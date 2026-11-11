"""Regenerate the bundled icon files from the procedural artwork in otoshi/icons.py.

python tools/build_icons.py            # writes otoshi/assets/icon.ico and icon.png
python tools/build_icons.py --preview  # also writes a contact sheet for review
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from otoshi import icons, theme  # noqa: E402

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = [icons.app_icon(s) for s in ICO_SIZES]
    frames[-1].save(
        out_dir / "icon.ico",
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=frames[:-1],
    )
    icons.app_icon(512).save(out_dir / "icon.png")
    icons.glyph("chevron", theme.MUTED, 48).save(out_dir / "chevron-down.png")
    for name, color in theme.ICON_VARIANTS.items():
        icons.app_icon(128, color).save(out_dir / f"app-{name}.png")
    print(f"wrote {out_dir / 'icon.ico'} and {out_dir / 'icon.png'}")


def preview(path: Path) -> None:
    sizes = [256, 128, 64, 48, 32, 24, 16]
    states = [theme.BRAND, theme.IDLE, theme.ROSE, theme.EMERALD, theme.VIOLET]
    glyphs = ["record", "stop", "play", "save", "open", "target", "cursor", "macro", "gear"]
    width = sum(sizes) + 20 * (len(sizes) + 1)
    sheet = Image.new("RGBA", (max(width, 760), 600), theme.BG)
    x = 20
    for s in sizes:
        sheet.alpha_composite(icons.app_icon(s), (x, 20))
        x += s + 20
    light = Image.new("RGBA", (width, 140), "#E4E4E7")
    x = 20
    for s in sizes[:4]:
        light.alpha_composite(icons.app_icon(s), (x, 6))
        x += s + 20
    sheet.alpha_composite(light.crop((0, 0, sheet.width, 140)), (0, 290))
    x = 20
    for c in states:
        for s in (32, 16):
            sheet.alpha_composite(icons.app_icon(s, c), (x, 450))
            x += s + 10
        x += 10
    x = 20
    for g in glyphs:
        sheet.alpha_composite(icons.glyph(g, theme.TEXT, 36), (x, 520))
        sheet.alpha_composite(icons.glyph(g, theme.MUTED, 18), (x + 9, 562))
        x += 56
    ImageDraw.Draw(sheet)
    sheet.save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path, nargs="?", const=ROOT / "icon_preview.png")
    args = parser.parse_args()
    build(ROOT / "otoshi" / "assets")
    if args.preview:
        preview(args.preview)
