"""Reusable CustomTkinter building blocks with the Otoshi look."""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, List, Optional, Sequence, Tuple, TypeVar

import customtkinter as ctk

from . import icons, theme
from .i18n import upper

T = TypeVar("T")


class Card(ctk.CTkFrame):
    """Rounded surface with an optional small-caps title and labelled rows."""

    def __init__(self, master: Any, title: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(
            master,
            fg_color=theme.SURFACE,
            corner_radius=theme.CARD_RADIUS,
            border_width=1,
            border_color=theme.BORDER,
            **kwargs,
        )
        top = 12 if title else 8
        if title:
            ctk.CTkLabel(
                self, text=upper(title), font=theme.font(11, "bold"), text_color=theme.DIM, anchor="w", height=18
            ).pack(fill="x", padx=16, pady=(top, 2))

    def row(self, label: str, hint: Optional[str] = None) -> ctk.CTkFrame:
        """A label (and optional hint) on the left; pack the control with ``side="right"``."""
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="y")
        ctk.CTkLabel(text, text=label, font=theme.font(13), text_color=theme.TEXT, anchor="w", height=20).pack(
            anchor="w"
        )
        if hint:
            ctk.CTkLabel(
                text,
                text=hint,
                font=theme.font(11),
                text_color=theme.DIM,
                anchor="w",
                justify="left",
                height=16,
                wraplength=230,
            ).pack(anchor="w")
        return row

    def finish(self) -> None:
        # Small and lifted off the edge: CTk children are drawn over the card border.
        ctk.CTkFrame(self, fg_color="transparent", width=1, height=8).pack(pady=(0, 2))


def primary_button(master: Any, color: str, hover: str, **kwargs: Any) -> ctk.CTkButton:
    return ctk.CTkButton(
        master,
        height=44,
        corner_radius=theme.RADIUS,
        fg_color=color,
        hover_color=hover,
        text_color="#FFFFFF",
        text_color_disabled=theme.DIM,
        font=theme.font(14, "bold"),
        **kwargs,
    )


def secondary_button(master: Any, **kwargs: Any) -> ctk.CTkButton:
    kwargs.setdefault("height", 34)
    return ctk.CTkButton(
        master,
        corner_radius=8,
        fg_color=theme.SURFACE_HI,
        hover_color=theme.HOVER,
        border_width=1,
        border_color=theme.BORDER,
        text_color=theme.TEXT,
        text_color_disabled=theme.DIM,
        font=theme.font(13, "bold"),
        **kwargs,
    )


def option_menu(
    master: Any, values: Sequence[str], command: Callable[[str], None], width: int = 128
) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(
        master,
        values=list(values),
        command=command,
        width=width,
        height=30,
        corner_radius=8,
        fg_color=theme.INPUT,
        button_color=theme.INPUT,
        button_hover_color=theme.HOVER,
        text_color=theme.TEXT,
        font=theme.font(13),
        dropdown_font=theme.font(13),
        dropdown_fg_color=theme.SURFACE_HI,
        dropdown_hover_color=theme.HOVER,
        dropdown_text_color=theme.TEXT,
        dynamic_resizing=False,
    )


def switch(master: Any, value: bool, command: Callable[[], None]) -> ctk.CTkSwitch:
    widget = ctk.CTkSwitch(
        master,
        text="",
        width=44,
        switch_width=40,
        switch_height=20,
        fg_color=theme.BORDER,
        progress_color=theme.BLUE,
        button_color=theme.TEXT,
        button_hover_color="#FFFFFF",
        command=command,
    )
    if value:
        widget.select()
    return widget


class ValidatedEntry(ctk.CTkEntry, Generic[T]):
    """Entry that parses its text on Enter/focus-out and reports valid values.

    ``parse`` raises ``ValueError`` with a user-facing message for bad input;
    the border turns red and ``on_error`` receives the message.
    """

    def __init__(
        self,
        master: Any,
        value: T,
        parse: Callable[[str], T],
        on_commit: Callable[[T], None],
        on_error: Callable[[str], None],
        fmt: Callable[[T], str] = str,
        width: int = 96,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=30,
            corner_radius=8,
            border_width=1,
            border_color=theme.BORDER,
            fg_color=theme.INPUT,
            text_color=theme.TEXT,
            font=theme.font(13),
            justify="center",
        )
        self._parse, self._on_commit, self._on_error, self._fmt = parse, on_commit, on_error, fmt
        self._value = value
        self._show(value)
        self.bind("<Return>", lambda _e: self.commit(), add=True)
        self.bind("<KP_Enter>", lambda _e: self.commit(), add=True)
        self.bind("<FocusOut>", lambda _e: self.commit(), add=True)
        self.bind("<Escape>", lambda _e: self.set_value(self._value), add=True)

    @property
    def value(self) -> T:
        return self._value

    def _show(self, value: T) -> None:
        state = self.cget("state")
        if state == "disabled":
            self.configure(state="normal")
        self.delete(0, "end")
        self.insert(0, self._fmt(value))
        if state == "disabled":
            self.configure(state="disabled")

    def set_value(self, value: T) -> None:
        """Programmatic update: no callback."""
        self._value = value
        self._show(value)
        self.configure(border_color=theme.BORDER)

    def commit(self) -> bool:
        if self.cget("state") == "disabled":
            return True
        try:
            value = self._parse(self.get())
        except ValueError as exc:
            self.configure(border_color=theme.ROSE)
            self._on_error(str(exc))
            return False
        self.configure(border_color=theme.BORDER)
        changed = value != self._value
        self._value = value
        self._show(value)
        if changed:
            self._on_commit(value)
        return True

    def set_enabled(self, enabled: bool) -> None:
        self.configure(state="normal" if enabled else "disabled", text_color=theme.TEXT if enabled else theme.DIM)


class SpeedBox(ctk.CTkComboBox):
    """Editable combo box for the playback speed (presets plus free input)."""

    PRESETS = ["0.5x", "1x", "1.5x", "2x", "3x", "5x", "10x", "20x"]

    def __init__(
        self,
        master: Any,
        value: float,
        parse: Callable[[str], float],
        fmt: Callable[[float], str],
        on_commit: Callable[[float], None],
        on_error: Callable[[str], None],
    ) -> None:
        super().__init__(
            master,
            values=self.PRESETS,
            width=110,
            height=30,
            corner_radius=8,
            border_width=1,
            border_color=theme.BORDER,
            fg_color=theme.INPUT,
            button_color=theme.INPUT,
            button_hover_color=theme.HOVER,
            text_color=theme.TEXT,
            font=theme.font(13),
            dropdown_font=theme.font(13),
            dropdown_fg_color=theme.SURFACE_HI,
            dropdown_hover_color=theme.HOVER,
            dropdown_text_color=theme.TEXT,
            justify="center",
            command=lambda _v: self.commit(),
        )
        self._parse, self._fmt, self._on_commit, self._on_error = parse, fmt, on_commit, on_error
        self._value = value
        self.set(fmt(value))
        self.bind("<Return>", lambda _e: self.commit(), add=True)
        self.bind("<FocusOut>", lambda _e: self.commit(), add=True)

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        self._value = value
        self.set(self._fmt(value))
        self.configure(border_color=theme.BORDER)

    def commit(self) -> bool:
        try:
            value = self._parse(self.get())
        except ValueError as exc:
            self.configure(border_color=theme.ROSE)
            self._on_error(str(exc))
            return False
        self.configure(border_color=theme.BORDER)
        changed = value != self._value
        self._value = value
        self.set(self._fmt(value))
        if changed:
            self._on_commit(value)
        return True


class NavBar(ctk.CTkFrame):
    """Segmented tab bar with icons."""

    def __init__(self, master: Any, items: List[Tuple[str, str, str]], command: Callable[[str], None]) -> None:
        super().__init__(
            master, fg_color=theme.SURFACE, corner_radius=theme.RADIUS + 2, border_width=1, border_color=theme.BORDER
        )
        self._command = command
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._icons: Dict[str, Tuple[str, str]] = {}
        for column, (key, label, icon) in enumerate(items):
            self.grid_columnconfigure(column, weight=1, uniform="nav")
            btn = ctk.CTkButton(
                self,
                text=label,
                height=34,
                corner_radius=theme.RADIUS - 2,
                font=theme.font(13, "bold"),
                compound="left",
                command=lambda k=key: self._on_click(k),
            )
            btn.grid(row=0, column=column, sticky="ew", padx=4, pady=4)
            self._buttons[key] = btn
            self._icons[key] = (icon, label)
        self.selected: Optional[str] = None

    def _on_click(self, key: str) -> None:
        if key != self.selected:
            self.select(key)
            self._command(key)

    def select(self, key: str) -> None:
        self.selected = key
        for k, btn in self._buttons.items():
            active = k == key
            btn.configure(
                fg_color=theme.SURFACE_HI if active else "transparent",
                hover_color=theme.HOVER,
                text_color=theme.TEXT if active else theme.MUTED,
                image=icons.ctk_glyph(self._icons[k][0], theme.TEXT if active else theme.DIM, 16),
            )


class Toast(ctk.CTkLabel):
    """One-line feedback message that fades back to an idle hint."""

    def __init__(self, master: Any, idle_text: str = "") -> None:
        super().__init__(
            master,
            text=idle_text,
            font=theme.font(12),
            text_color=theme.DIM,
            anchor="w",
            justify="left",
            height=22,
            wraplength=400,
        )
        self._idle_text = idle_text
        self._after: Optional[str] = None

    def show(self, text: str, level: str = "info", duration_ms: int = 3500) -> None:
        if self._after is not None:
            self.after_cancel(self._after)
        self.configure(text=text, text_color=theme.LEVEL_COLORS.get(level, theme.MUTED))
        self._after = self.after(duration_ms, self._reset)

    def clear(self) -> None:
        if self._after is not None:
            self.after_cancel(self._after)
        self._reset()

    def _reset(self) -> None:
        self._after = None
        self.configure(text=self._idle_text, text_color=theme.DIM)


class StatusPill(ctk.CTkFrame):
    def __init__(self, master: Any) -> None:
        super().__init__(
            master, fg_color=theme.SURFACE, corner_radius=14, border_width=1, border_color=theme.BORDER, height=28
        )
        self._dot = ctk.CTkLabel(self, text="●", font=theme.font(12), text_color=theme.IDLE, width=12, height=24)
        self._dot.pack(side="left", padx=(12, 6), pady=1)
        self._label = ctk.CTkLabel(self, text="Ready", font=theme.font(12, "bold"), text_color=theme.MUTED, height=24)
        self._label.pack(side="left", padx=(0, 14), pady=1)

    def set(self, text: str, color: str) -> None:
        self._dot.configure(text_color=color)
        self._label.configure(text=text, text_color=theme.TEXT if color != theme.IDLE else theme.MUTED)
