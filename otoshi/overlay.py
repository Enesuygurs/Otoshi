"""Always-on-top helper windows: the status overlay and the location picker.

Both use plain Tk toplevels (not CTk) so their geometry is in real screen
pixels, which is what the mouse controller uses as well.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional, Tuple

from PIL import Image, ImageDraw, ImageTk

from . import theme
from .i18n import t
from .winutil import make_click_through, toplevel_hwnd, virtual_screen, work_area

_KEY = "#010203"  # colour made fully transparent on Windows


def _rgb(color: str) -> Tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


class StatusOverlay(tk.Toplevel):
    """Small click-through pill in a screen corner showing the current mode."""

    MARGIN = 16

    def __init__(self, master: tk.Misc, position: str = "top-left") -> None:
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", _KEY)
            self.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        self.configure(bg=_KEY)
        self._canvas = tk.Canvas(self, bg=_KEY, highlightthickness=0, bd=0)
        self._canvas.pack()
        self._scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self._font = tkfont.Font(family=theme.FONT_FAMILY, size=10, weight="bold")
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._position = position
        self._click_through = False
        self._state: Tuple[str, str] = ("", "")
        self.set_status("Ready", theme.IDLE)

    def set_status(self, text: str, color: str) -> None:
        if (text, color) == self._state:
            return
        self._state = (text, color)
        s = self._scale
        pad_x, dot_d, gap = round(12 * s), round(8 * s), round(8 * s)
        text_w = self._font.measure(text)
        h = self._font.metrics("linespace") + round(12 * s)
        w = pad_x + dot_d + gap + text_w + pad_x

        ss = 4
        img = Image.new("RGB", (w * ss, h * ss), _rgb(_KEY))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [0, 0, w * ss - 1, h * ss - 1],
            radius=h * ss // 2,
            fill=_rgb(theme.SURFACE),
            outline=_rgb(theme.BORDER),
            width=ss,
        )
        cy = h * ss / 2
        d.ellipse([pad_x * ss, cy - dot_d * ss / 2, (pad_x + dot_d) * ss, cy + dot_d * ss / 2], fill=_rgb(color))
        self._photo = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))

        c = self._canvas
        c.delete("all")
        c.configure(width=w, height=h)
        c.create_image(0, 0, anchor="nw", image=self._photo)
        c.create_text(pad_x + dot_d + gap, h / 2, text=text, anchor="w", fill=theme.TEXT, font=self._font)
        self._place(w, h)

    def set_font_family(self, family: str) -> None:
        self._font.configure(family=family)
        text, color = self._state
        self._state = ("", "")
        self.set_status(text, color)

    def set_position(self, position: str) -> None:
        self._position = position
        self._place(int(self._canvas.cget("width")), int(self._canvas.cget("height")))

    def _place(self, w: int, h: int) -> None:
        left, top, right, bottom = work_area((0, 0, self.winfo_screenwidth(), self.winfo_screenheight()))
        m = round(self.MARGIN * self._scale)
        x = left + m if "left" in self._position else right - w - m
        y = top + m if "top" in self._position else bottom - h - m
        self.geometry(f"{w}x{h}+{x}+{y}")

    def show(self) -> None:
        self.deiconify()
        self.lift()
        if not self._click_through:
            self.update_idletasks()
            make_click_through(toplevel_hwnd(self))
            self._click_through = True

    def hide(self) -> None:
        self.withdraw()


class LocationPicker:
    """Dims every monitor and reports the screen position of the next click.

    Esc or right-click cancels. ``on_done`` receives ``(x, y)`` or ``None``.
    """

    def __init__(self, master: tk.Misc, on_done: Callable[[Optional[Tuple[int, int]]], None]) -> None:
        self._on_done = on_done
        self._finished = False
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        x0, y0, x1, y1 = virtual_screen((0, 0, sw, sh))

        self.shade = tk.Toplevel(master)
        self.shade.overrideredirect(True)
        self.shade.attributes("-topmost", True)
        try:
            self.shade.attributes("-alpha", 0.35)
        except tk.TclError:
            pass
        self.shade.configure(bg="#000000", cursor="crosshair")
        self.shade.geometry(f"{x1 - x0}x{y1 - y0}+{x0}+{y0}")

        scale = max(1.0, master.winfo_fpixels("1i") / 96.0)
        self.hint = tk.Toplevel(master)
        self.hint.overrideredirect(True)
        self.hint.attributes("-topmost", True)
        self.hint.configure(bg=theme.SURFACE, highlightthickness=1, highlightbackground=theme.BORDER)
        title_font = tkfont.Font(family=theme.FONT_FAMILY, size=11, weight="bold")
        body_font = tkfont.Font(family=theme.FONT_FAMILY, size=10)
        tk.Label(self.hint, text=t("picker_title"), bg=theme.SURFACE, fg=theme.TEXT, font=title_font).pack(
            padx=round(18 * scale), pady=(round(10 * scale), 0)
        )
        self._coords = tk.Label(self.hint, text="", bg=theme.SURFACE, fg=theme.VIOLET, font=title_font)
        self._coords.pack()
        tk.Label(self.hint, text=t("picker_cancel"), bg=theme.SURFACE, fg=theme.DIM, font=body_font).pack(
            padx=round(18 * scale), pady=(0, round(10 * scale))
        )
        self.hint.update_idletasks()
        hw = self.hint.winfo_reqwidth()
        self.hint.geometry(f"+{(sw - hw) // 2}+{round(40 * scale)}")

        for widget in (self.shade, self.hint):
            widget.bind("<Button-1>", self._pick)
            widget.bind("<Button-3>", lambda _e: self._finish(None))
            widget.bind("<Escape>", lambda _e: self._finish(None))
            widget.bind("<Motion>", self._track)
        self.shade.focus_force()
        self.shade.grab_set()

    def _track(self, event: tk.Event) -> None:
        self._coords.configure(text=f"X {event.x_root}   Y {event.y_root}")

    def _pick(self, event: tk.Event) -> None:
        self._finish((event.x_root, event.y_root))

    def _finish(self, result: Optional[Tuple[int, int]]) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            self.shade.grab_release()
        except tk.TclError:
            pass
        self.shade.destroy()
        self.hint.destroy()
        self._on_done(result)
