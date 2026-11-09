"""Otoshi main window.

Threading model: Tk may only be touched from the main thread. Hotkeys, the
tray menu and the engine worker threads therefore never call widgets directly;
they post callables with :meth:`OtoshiApp.dispatch`, which the main loop drains
every few milliseconds.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
import tkinter as tk
from enum import Enum
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from . import APP_NAME, __version__, i18n, icons, theme
from .clicker import AutoClicker
from .config import (
    BUTTONS,
    CLICK_TYPES,
    CLICKS_MAX,
    COORD_LIMIT,
    COUNTDOWN_MAX,
    DEFAULT_HOTKEYS,
    INTERVAL_MAX_MS,
    INTERVAL_MIN_MS,
    LOCATIONS,
    LOOPS_MAX,
    OVERLAY_POSITIONS,
    Settings,
    format_speed,
    int_parser,
    load_settings,
    parse_speed,
    save_settings,
)
from .hotkeys import ERROR_IN_USE, HotkeyManager, format_hotkey, trigger_for, validate_hotkey
from .i18n import number, t
from .logger import logger, setup_logging
from .macro import MacroEngine, MacroFileError, load_macro, save_macro
from .overlay import LocationPicker, StatusOverlay
from .paths import asset, data_dir
from .tray import TrayIcon
from .widgets import (
    Card,
    NavBar,
    SpeedBox,
    StatusPill,
    Toast,
    ValidatedEntry,
    option_menu,
    primary_button,
    secondary_button,
    switch,
)
from .winutil import acquire_single_instance, open_folder, set_app_user_model_id

ACTIONS = ("record", "play", "clicker")
HOTKEY_DEBOUNCE_S = 0.25


class Mode(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    COUNTDOWN = "countdown"
    PLAYING = "playing"
    CLICKING = "clicking"


MODE_STYLE = {
    Mode.IDLE: ("mode_ready", theme.IDLE),
    Mode.RECORDING: ("mode_recording", theme.ROSE),
    Mode.COUNTDOWN: ("mode_countdown", theme.AMBER),
    Mode.PLAYING: ("mode_playing", theme.EMERALD),
    Mode.CLICKING: ("mode_clicking", theme.VIOLET),
}


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return t("duration_seconds", seconds=f"{seconds:.1f}")
    minutes, secs = divmod(int(seconds), 60)
    return t("duration_minutes", minutes=minutes, seconds=f"{secs:02d}")


def _choice(values: Tuple[str, ...], prefix: str) -> Tuple[List[str], Dict[str, str]]:
    """Translated labels for a set of setting values, plus label -> value lookup."""
    labels = [t(f"{prefix}_{v.replace('-', '_')}") for v in values]
    return labels, dict(zip(labels, values))


class OtoshiApp(ctk.CTk):
    WIDTH, HEIGHT = 440, 620

    def __init__(self, settings: Settings) -> None:
        super().__init__(fg_color=theme.BG)
        self.settings = settings
        self.mode = Mode.IDLE

        self.macro = MacroEngine()
        self.clicker = AutoClicker()
        self.hotkeys = HotkeyManager()

        self._queue: queue.SimpleQueue[Tuple[Callable[..., Any], tuple]] = queue.SimpleQueue()
        self._play_token: Optional[object] = None
        self._click_token: Optional[object] = None
        self._countdown_left = 0
        self._countdown_job: Optional[str] = None
        self._tick_job: Optional[str] = None
        self._last_hotkey: Dict[str, float] = {}
        self._capturing: Optional[str] = None
        self._macro_name: Optional[str] = None
        self._tray_hint_shown = False
        self._closing = False
        self._picker: Optional[LocationPicker] = None

        self.title(APP_NAME)
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.resizable(False, False)
        self._set_window_icon()
        self.report_callback_exception = self._on_tk_error  # type: ignore[assignment]

        self._build_ui()

        self.overlay = StatusOverlay(self, settings.overlay_position)
        self.tray = TrayIcon(APP_NAME, icons.app_icon(64, theme.IDLE), APP_NAME, self._tray_menu())

        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.bind("<Unmap>", self._on_unmap)

        self._bind_hotkeys(initial=True)
        self._set_mode(Mode.IDLE)
        self.after(20, self._drain_queue)
        self.after(150, self._start_background)
        logger.info("Otoshi %s started (language: %s)", __version__, i18n.language())

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------
    def dispatch(self, fn: Callable[..., Any], *args: Any) -> None:
        """Run ``fn(*args)`` on the Tk main thread. Safe to call from any thread."""
        self._queue.put((fn, args))

    def _drain_queue(self) -> None:
        while True:
            try:
                fn, args = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:
                logger.exception("UI callback %s failed", getattr(fn, "__name__", fn))
        if not self._closing:
            self.after(20, self._drain_queue)

    def _on_tk_error(self, exc_type, exc, tb) -> None:
        logger.error("Unhandled UI error", exc_info=(exc_type, exc, tb))
        self.toast.show(t("msg_ui_error"), "error", 6000)

    def _set_window_icon(self) -> None:
        try:
            self.iconbitmap(default=str(asset("icon.ico")))
        except tk.TclError:
            logger.warning("Could not load window icon", exc_info=True)

    def _start_background(self) -> None:
        if self.settings.show_overlay:
            self.overlay.show()
        if not self.tray.start():
            self.toast.show(t("msg_tray_unavailable"), "warning")

    def _tray_menu(self):
        return [
            (t("tray_show"), lambda: self.dispatch(self.show_window), True),
            None,
            (t("action_record"), lambda: self.dispatch(self.toggle_recording), False),
            (t("action_play"), lambda: self.dispatch(self.toggle_playback), False),
            (t("action_clicker"), lambda: self.dispatch(self.toggle_clicker), False),
            None,
            (t("tray_quit"), lambda: self.dispatch(self.quit_app), False),
        ]

    def _save(self) -> None:
        save_settings(self.settings)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        pad = theme.PAD

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=pad, pady=(16, 12))
        ctk.CTkLabel(header, text="", image=icons.ctk_logo(28), width=28).pack(side="left")
        ctk.CTkLabel(header, text=APP_NAME, font=theme.font(20, "bold"), text_color=theme.TEXT).pack(
            side="left", padx=(10, 0)
        )
        self.status_pill = StatusPill(header)
        self.status_pill.pack(side="right")

        self.nav = NavBar(
            self,
            [
                ("macro", t("nav_macro"), "macro"),
                ("clicker", t("nav_clicker"), "cursor"),
                ("settings", t("nav_settings"), "gear"),
            ],
            self._show_page,
        )
        self.nav.grid(row=1, column=0, sticky="ew", padx=pad, pady=(0, 12))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew", padx=pad)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.pages: Dict[str, ctk.CTkFrame] = {}
        for key in ("macro", "clicker", "settings"):
            page = ctk.CTkFrame(content, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        self.toast = Toast(self, idle_text=t("toast_idle"))
        self.toast.grid(row=3, column=0, sticky="ew", padx=pad + 2, pady=(6, 12))

        self._build_macro_page(self.pages["macro"])
        self._build_clicker_page(self.pages["clicker"])
        self._build_settings_page(self.pages["settings"])
        self.nav.select("macro")
        self._show_page("macro")

    def _show_page(self, key: str) -> None:
        if self._capturing:
            self._finish_capture(self._capturing, None)
        self.pages[key].tkraise()

    def _build_macro_page(self, page: ctk.CTkFrame) -> None:
        s = self.settings
        rec = Card(page, t("card_recorder"))
        rec.pack(fill="x")
        buttons = ctk.CTkFrame(rec, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=(6, 4))
        self.record_btn = primary_button(buttons, theme.ROSE, theme.ROSE_HOVER, command=self.toggle_recording)
        self.record_btn.pack(fill="x")
        self.play_btn = primary_button(buttons, theme.EMERALD, theme.EMERALD_HOVER, command=self.toggle_playback)
        self.play_btn.pack(fill="x", pady=(8, 0))

        self.macro_info = ctk.CTkLabel(
            rec, text="", font=theme.font(12), text_color=theme.MUTED, anchor="w", justify="left", wraplength=360
        )
        self.macro_info.pack(fill="x", padx=18, pady=(8, 4))

        files = ctk.CTkFrame(rec, fg_color="transparent")
        files.pack(fill="x", padx=16, pady=(2, 14))
        files.grid_columnconfigure((0, 1), weight=1, uniform="files")
        self.save_btn = secondary_button(
            files, text=t("btn_save"), image=icons.ctk_glyph("save", theme.TEXT, 16), command=self.save_macro_dialog
        )
        self.save_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.load_btn = secondary_button(
            files, text=t("btn_open"), image=icons.ctk_glyph("open", theme.TEXT, 16), command=self.load_macro_dialog
        )
        self.load_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        play = Card(page, t("card_playback"))
        play.pack(fill="x", pady=(12, 0))
        self.loop_entry = ValidatedEntry(
            play.row(t("row_repeat"), t("hint_repeat_loops")),
            s.macro_loop_count,
            int_parser(t("row_repeat"), 0, LOOPS_MAX),
            lambda v: self._update_setting("macro_loop_count", v),
            self._input_error,
        )
        self.loop_entry.pack(side="right")
        self.speed_box = SpeedBox(
            play.row(t("row_speed"), "0.1x – 100x"),
            s.playback_speed,
            parse_speed,
            format_speed,
            lambda v: self._update_setting("playback_speed", v),
            self._input_error,
        )
        self.speed_box.pack(side="right")
        self.countdown_entry = ValidatedEntry(
            play.row(t("row_countdown"), t("hint_countdown")),
            s.countdown_seconds,
            int_parser(t("row_countdown"), 0, COUNTDOWN_MAX),
            lambda v: self._update_setting("countdown_seconds", v),
            self._input_error,
        )
        self.countdown_entry.pack(side="right")
        play.finish()

    def _build_clicker_page(self, page: ctk.CTkFrame) -> None:
        s = self.settings
        card = Card(page, t("card_clicking"))
        card.pack(fill="x")
        self.interval_entry = ValidatedEntry(
            card.row(t("row_interval"), t("hint_interval")),
            s.ac_interval_ms,
            int_parser(t("row_interval"), INTERVAL_MIN_MS, INTERVAL_MAX_MS),
            lambda v: self._update_setting("ac_interval_ms", v),
            self._input_error,
        )
        self.interval_entry.pack(side="right")

        labels, lookup = _choice(BUTTONS, "button")
        self.button_menu = option_menu(
            card.row(t("row_mouse_button")), labels, lambda v: self._update_setting("ac_button", lookup[v])
        )
        self.button_menu.set(labels[BUTTONS.index(s.ac_button)])
        self.button_menu.pack(side="right")

        labels, lookup = _choice(CLICK_TYPES, "click")
        self.type_menu = option_menu(
            card.row(t("row_click_type")), labels, lambda v: self._update_setting("ac_click_type", lookup[v])
        )
        self.type_menu.set(labels[CLICK_TYPES.index(s.ac_click_type)])
        self.type_menu.pack(side="right")

        self.clicks_entry = ValidatedEntry(
            card.row(t("row_repeat"), t("hint_repeat_clicks")),
            s.ac_click_times,
            int_parser(t("row_repeat"), 0, CLICKS_MAX),
            lambda v: self._update_setting("ac_click_times", v),
            self._input_error,
        )
        self.clicks_entry.pack(side="right")
        card.finish()

        pos = Card(page, t("card_position"))
        pos.pack(fill="x", pady=(12, 0))
        labels, self._location_lookup = _choice(LOCATIONS, "location")
        self.location_seg = ctk.CTkSegmentedButton(
            pos.row(t("row_click_at")),
            values=labels,
            command=self._on_location_change,
            height=30,
            corner_radius=8,
            font=theme.font(13, "bold"),
            fg_color=theme.INPUT,
            selected_color=theme.VIOLET,
            selected_hover_color=theme.VIOLET_HOVER,
            unselected_color=theme.INPUT,
            unselected_hover_color=theme.HOVER,
            text_color=theme.TEXT,
        )
        self.location_seg.set(labels[LOCATIONS.index(s.ac_location)])
        self.location_seg.pack(side="right")

        coords = pos.row(t("row_coordinates"), t("hint_coordinates"))
        self.pick_btn = secondary_button(
            coords,
            text="",
            width=34,
            height=30,
            image=icons.ctk_glyph("target", theme.TEXT, 16),
            command=self.pick_location,
        )
        self.pick_btn.pack(side="right", padx=(6, 0))
        coord_parser = int_parser(t("label_coordinate"), -COORD_LIMIT, COORD_LIMIT)
        self.y_entry = ValidatedEntry(
            coords, s.ac_y, coord_parser, lambda v: self._update_setting("ac_y", v), self._input_error, width=64
        )
        self.y_entry.pack(side="right", padx=(6, 0))
        self.x_entry = ValidatedEntry(
            coords, s.ac_x, coord_parser, lambda v: self._update_setting("ac_x", v), self._input_error, width=64
        )
        self.x_entry.pack(side="right")
        pos.finish()

        self.clicker_btn = primary_button(page, theme.VIOLET, theme.VIOLET_HOVER, command=self.toggle_clicker)
        self.clicker_btn.pack(fill="x", pady=(14, 0))

    def _build_settings_page(self, page: ctk.CTkFrame) -> None:
        s = self.settings
        keys = Card(page, t("card_hotkeys"))
        keys.pack(fill="x")
        self.hotkey_btns: Dict[str, ctk.CTkButton] = {}
        for action in ACTIONS:
            btn = ctk.CTkButton(
                keys.row(t(f"action_{action}")),
                width=128,
                height=30,
                corner_radius=8,
                fg_color=theme.INPUT,
                hover_color=theme.HOVER,
                border_width=1,
                border_color=theme.BORDER,
                text_color=theme.TEXT,
                text_color_disabled=theme.DIM,
                font=theme.font(13, "bold"),
                command=lambda a=action: self._begin_capture(a),
            )
            btn.pack(side="right")
            self.hotkey_btns[action] = btn
        keys.finish()

        ui = Card(page, t("card_interface"))
        ui.pack(fill="x", pady=(12, 0))
        language_names = list(i18n.LANGUAGES.values())
        self.language_menu = option_menu(ui.row(t("row_language")), language_names, self._on_language)
        self.language_menu.set(i18n.LANGUAGES[i18n.language()])
        self.language_menu.pack(side="right")

        self.overlay_switch = switch(ui.row(t("row_overlay")), s.show_overlay, self._on_overlay_toggle)
        self.overlay_switch.pack(side="right")
        labels, self._overlay_lookup = _choice(OVERLAY_POSITIONS, "position")
        self.overlay_menu = option_menu(ui.row(t("row_overlay_position")), labels, self._on_overlay_position, width=156)
        self.overlay_menu.set(labels[OVERLAY_POSITIONS.index(s.overlay_position)])
        self.overlay_menu.pack(side="right")
        self.close_switch = switch(
            ui.row(t("row_close_to_tray")), s.close_to_tray, lambda: self._on_switch("close_to_tray", self.close_switch)
        )
        self.close_switch.pack(side="right")
        self.minimize_switch = switch(
            ui.row(t("row_minimize_to_tray")),
            s.minimize_to_tray,
            lambda: self._on_switch("minimize_to_tray", self.minimize_switch),
        )
        self.minimize_switch.pack(side="right")
        ui.finish()

        about = ctk.CTkFrame(page, fg_color="transparent")
        about.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(about, text=f"{APP_NAME} {__version__}", font=theme.font(12, "bold"), text_color=theme.DIM).pack(
            side="left", padx=(2, 0)
        )
        secondary_button(
            about,
            text=t("btn_data_folder"),
            height=30,
            image=icons.ctk_glyph("folder", theme.TEXT, 15),
            command=lambda: open_folder(data_dir()),
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------
    def _on_language(self, name: str) -> None:
        code = next(c for c, n in i18n.LANGUAGES.items() if n == name)
        if code == i18n.language():
            return
        self._update_setting("language", code)
        # Rebuild after the option menu's own callback has returned.
        self.after(10, lambda: self._apply_language(code))

    def _apply_language(self, code: str) -> None:
        if self._capturing:
            self._finish_capture(self._capturing, None)
        page = self.nav.selected or "macro"
        i18n.set_language(code)
        theme.set_font_family(i18n.font_family(code))
        for child in self.winfo_children():
            if not isinstance(child, tk.Toplevel):  # keep the overlay / picker windows
                child.destroy()
        self._build_ui()
        self.nav.select(page)
        self._show_page(page)
        self.overlay.set_font_family(theme.FONT_FAMILY)
        self.tray.set_menu(self._tray_menu())
        self._set_mode(self.mode)
        logger.info("Language changed to %s", code)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def _set_mode(self, mode: Mode) -> None:
        self.mode = mode
        self._refresh_controls()
        self._refresh_status()
        label, color = MODE_STYLE[mode]
        self.tray.update(icons.app_icon(64, color), f"{APP_NAME}: {t(label)}")
        if mode is Mode.COUNTDOWN:
            self.overlay.show()  # visible even when the overlay is off: the user is looking at another window
        elif self.settings.show_overlay:
            self.overlay.show()
        else:
            self.overlay.hide()
        if mode is not Mode.IDLE and self._tick_job is None:
            self._tick_job = self.after(250, self._tick_status)

    def _status_text(self) -> str:
        if self.mode is Mode.RECORDING:
            return t("status_recording", seconds=f"{self.macro.recording_elapsed:.0f}")
        if self.mode is Mode.COUNTDOWN:
            return t("status_countdown", seconds=self._countdown_left)
        if self.mode is Mode.PLAYING:
            total = self.settings.macro_loop_count
            return t("status_playing", loop=self.macro.current_loop, total=total if total else "∞")
        if self.mode is Mode.CLICKING:
            return t("status_clicking", count=number(self.clicker.clicks_done))
        return t(MODE_STYLE[Mode.IDLE][0])

    def _refresh_status(self) -> None:
        text, color = self._status_text(), MODE_STYLE[self.mode][1]
        self.status_pill.set(text, color)
        self.overlay.set_status(text, color)

    def _tick_status(self) -> None:
        self._tick_job = None
        if self.mode is Mode.IDLE or self._closing:
            return
        self._refresh_status()
        self._tick_job = self.after(250, self._tick_status)

    def _refresh_controls(self) -> None:
        mode, s = self.mode, self.settings
        idle = mode is Mode.IDLE
        has_macro = bool(self.macro.events)
        white = "#FFFFFF"

        def hk(action: str) -> str:
            return format_hotkey(s.hotkey(action))

        def label(key: str, action: str, **kw: Any) -> str:
            return f"{t(key, **kw)}  ·  {hk(action)}"

        if mode is Mode.RECORDING:
            self.record_btn.configure(
                text=label("btn_stop_recording", "record"),
                image=icons.ctk_glyph("stop", white, 18),
                fg_color=theme.ROSE_HOVER,
                state="normal",
            )
        else:
            self.record_btn.configure(
                text=label("btn_record", "record"),
                image=icons.ctk_glyph("record", white if idle else theme.DIM, 18),
                fg_color=theme.ROSE if idle else theme.SURFACE_HI,
                state="normal" if idle else "disabled",
            )

        if mode is Mode.PLAYING:
            self.play_btn.configure(
                text=label("btn_stop_playback", "play"),
                image=icons.ctk_glyph("stop", white, 18),
                fg_color=theme.EMERALD_HOVER,
                hover_color=theme.EMERALD_HOVER,
                state="normal",
            )
        elif mode is Mode.COUNTDOWN:
            self.play_btn.configure(
                text=label("btn_cancel_countdown", "play", seconds=self._countdown_left),
                image=icons.ctk_glyph("stop", white, 18),
                fg_color=theme.AMBER,
                hover_color=theme.AMBER,
                state="normal",
            )
        else:
            can_play = idle and has_macro
            self.play_btn.configure(
                text=label("btn_play", "play"),
                image=icons.ctk_glyph("play", white if can_play else theme.DIM, 18),
                fg_color=theme.EMERALD if can_play else theme.SURFACE_HI,
                hover_color=theme.EMERALD_HOVER,
                state="normal" if can_play else "disabled",
            )

        if mode is Mode.CLICKING:
            self.clicker_btn.configure(
                text=label("btn_stop_clicking", "clicker"),
                image=icons.ctk_glyph("stop", white, 18),
                fg_color=theme.VIOLET_HOVER,
                state="normal",
            )
        else:
            self.clicker_btn.configure(
                text=label("btn_start_clicking", "clicker"),
                image=icons.ctk_glyph("cursor", white if idle else theme.DIM, 18),
                fg_color=theme.VIOLET if idle else theme.SURFACE_HI,
                state="normal" if idle else "disabled",
            )

        self.save_btn.configure(state="normal" if idle and has_macro else "disabled")
        self.load_btn.configure(state="normal" if idle else "disabled")
        for action, btn in self.hotkey_btns.items():
            if self._capturing != action:
                btn.configure(
                    text=hk(action),
                    text_color=theme.TEXT,
                    border_color=theme.BORDER,
                    state="normal" if idle else "disabled",
                )
        fixed = self.settings.ac_location == "fixed"
        for entry in (self.x_entry, self.y_entry):
            entry.set_enabled(fixed and idle)
        self.pick_btn.configure(state="normal" if fixed and idle else "disabled")
        self._refresh_macro_info()

    def _refresh_macro_info(self) -> None:
        events = self.macro.events
        if self.mode is Mode.RECORDING:
            text = t("info_recording")
        elif not events:
            text = t("info_empty", hotkey=format_hotkey(self.settings.record_hotkey))
        else:
            name = f"  ·  {self._macro_name}" if self._macro_name else ""
            text = f"{t('info_events', count=number(len(events)))}  ·  {_fmt_duration(self.macro.duration)}{name}"
        self.macro_info.configure(text=text)

    def _busy(self) -> None:
        self.toast.show(t("msg_busy", mode=t(MODE_STYLE[self.mode][0]).lower()), "warning")

    def _input_error(self, message: str) -> None:
        self.toast.show(message, "error", 5000)

    def _update_setting(self, name: str, value: Any) -> None:
        setattr(self.settings, name, value)
        self._save()

    def _commit_inputs(self, *entries: Any) -> bool:
        return all([e.commit() for e in entries])  # list: validate every field, not just until the first error

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------
    def _bind_hotkeys(self, initial: bool = False) -> None:
        if initial:
            for action in ACTIONS:
                error = validate_hotkey(self.settings.hotkey(action))
                if error:
                    logger.warning(
                        "Invalid %s hotkey %r (%s); using default", action, self.settings.hotkey(action), error
                    )
                    self.settings.set_hotkey(action, DEFAULT_HOTKEYS[action])
            if len({self.settings.hotkey(a) for a in ACTIONS}) < len(ACTIONS):
                for action in ACTIONS:
                    self.settings.set_hotkey(action, DEFAULT_HOTKEYS[action])
            self._save()

        bindings = {a: (self.settings.hotkey(a), (lambda a=a: self.dispatch(self._on_hotkey, a))) for a in ACTIONS}
        errors = self.hotkeys.bind(bindings)
        if errors:
            names = ", ".join(format_hotkey(self.settings.hotkey(a)) for a in errors)
            if len(errors) == 1 and ERROR_IN_USE in errors.values():
                message = t("hk_err_in_use", hotkey=names)
            else:
                message = t("msg_hotkeys_failed", hotkeys=names)
            self.toast.show(message, "error", 8000)

    def _on_hotkey(self, action: str) -> None:
        now = time.monotonic()
        if now - self._last_hotkey.get(action, 0.0) < HOTKEY_DEBOUNCE_S:
            return
        self._last_hotkey[action] = now
        {"record": self.toggle_recording, "play": self.toggle_playback, "clicker": self.toggle_clicker}[action]()

    def _begin_capture(self, action: str) -> None:
        if self._capturing == action:
            self._finish_capture(action, None)
            return
        if self._capturing:
            self._finish_capture(self._capturing, None)
        if self.mode is not Mode.IDLE:
            self._busy()
            return
        self._capturing = action
        self.hotkeys.unbind_all()  # so pressing F2 now does not start a recording
        self.focus_set()
        self.hotkey_btns[action].configure(text=t("press_keys"), text_color=theme.ROSE, border_color=theme.ROSE)
        self.toast.show(t("hotkeys_help"), "info", 10000)
        self.hotkeys.capture(lambda result: self.dispatch(self._finish_capture, action, result))

    def _finish_capture(self, action: str, result: Optional[str]) -> None:
        if self._capturing != action:
            return
        self._capturing = None
        self.hotkeys.cancel_capture()
        if result is None:
            self.toast.clear()
        else:
            error = validate_hotkey(result)
            clash = next((a for a in ACTIONS if a != action and self.settings.hotkey(a) == result), None)
            if error:
                self.toast.show(error, "error", 6000)
            elif clash:
                self.toast.show(
                    t("msg_hotkey_clash", hotkey=format_hotkey(result), action=t(f"action_{clash}")), "error", 6000
                )
            else:
                self.settings.set_hotkey(action, result)
                self._save()
                self.toast.show(
                    t("msg_hotkey_set", action=t(f"action_{action}"), hotkey=format_hotkey(result)), "success"
                )
        self._bind_hotkeys()
        self._refresh_controls()

    # ------------------------------------------------------------------
    # Recording / playback
    # ------------------------------------------------------------------
    def toggle_recording(self) -> None:
        if self.mode is Mode.RECORDING:
            self._stop_recording()
        elif self.mode is Mode.IDLE:
            self._start_recording()
        else:
            self._busy()

    def _start_recording(self) -> None:
        triggers = [tr for tr in (trigger_for(self.settings.hotkey(a)) for a in ACTIONS) if tr is not None]
        if not self.macro.start_recording(triggers):
            self.toast.show(t("msg_record_failed"), "error")
            return
        logger.info("Recording started")
        self._set_mode(Mode.RECORDING)

    def _stop_recording(self) -> None:
        count = self.macro.stop_recording(exclude_rect=self._window_rect())
        logger.info("Recording stopped: %d events", count)
        if count:
            self._macro_name = None
            self.toast.show(t("msg_recorded", count=number(count)), "success")
        else:
            self.toast.show(t("msg_nothing_recorded"), "warning")
        self._set_mode(Mode.IDLE)

    def _window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        if self.state() != "normal" or not self.winfo_viewable():
            return None
        x, y = self.winfo_rootx(), self.winfo_rooty()
        return x, y, x + self.winfo_width(), y + self.winfo_height()

    def toggle_playback(self) -> None:
        if self.mode is Mode.PLAYING:
            self.macro.stop_playback()
            self._set_mode(Mode.IDLE)
            self.toast.show(t("msg_playback_stopped"))
        elif self.mode is Mode.COUNTDOWN:
            self._cancel_countdown()
            self._set_mode(Mode.IDLE)
            self.toast.show(t("msg_playback_cancelled"))
        elif self.mode is Mode.IDLE:
            self._request_playback()
        else:
            self._busy()

    def _request_playback(self) -> None:
        if not self.macro.events:
            self.toast.show(t("msg_no_macro"), "warning")
            return
        if not self._commit_inputs(self.loop_entry, self.speed_box, self.countdown_entry):
            return
        if self.settings.countdown_seconds <= 0:
            self._start_playback()
            return
        self._countdown_left = self.settings.countdown_seconds
        self._set_mode(Mode.COUNTDOWN)
        self._countdown_job = self.after(1000, self._countdown_tick)

    def _countdown_tick(self) -> None:
        self._countdown_job = None
        if self.mode is not Mode.COUNTDOWN:
            return
        self._countdown_left -= 1
        if self._countdown_left <= 0:
            self._start_playback()
            return
        self._refresh_controls()
        self._refresh_status()
        self._countdown_job = self.after(1000, self._countdown_tick)

    def _cancel_countdown(self) -> None:
        if self._countdown_job is not None:
            self.after_cancel(self._countdown_job)
            self._countdown_job = None

    def _start_playback(self) -> None:
        token = object()
        self._play_token = token
        started = self.macro.play(
            self.settings.macro_loop_count,
            self.settings.playback_speed,
            on_finish=lambda: self.dispatch(self._on_playback_finished, token),
        )
        if started:
            logger.info(
                "Playback started (loops=%s, speed=%s)", self.settings.macro_loop_count, self.settings.playback_speed
            )
            self._set_mode(Mode.PLAYING)
        else:
            self._set_mode(Mode.IDLE)

    def _on_playback_finished(self, token: object) -> None:
        if token is self._play_token and self.mode is Mode.PLAYING:
            self._set_mode(Mode.IDLE)
            self.toast.show(t("msg_playback_finished"), "success")

    # ------------------------------------------------------------------
    # Auto clicker
    # ------------------------------------------------------------------
    def toggle_clicker(self) -> None:
        if self.mode is Mode.CLICKING:
            self.clicker.stop()
            self._set_mode(Mode.IDLE)
            self.toast.show(t("msg_clicker_stopped", count=number(self.clicker.clicks_done)))
        elif self.mode is Mode.IDLE:
            self._start_clicker()
        else:
            self._busy()

    def _start_clicker(self) -> None:
        if not self._commit_inputs(self.interval_entry, self.clicks_entry, self.x_entry, self.y_entry):
            return
        s = self.settings
        token = object()
        self._click_token = token
        position = (s.ac_x, s.ac_y) if s.ac_location == "fixed" else None
        started = self.clicker.start(
            s.ac_interval_ms,
            s.ac_button,
            s.ac_click_type,
            s.ac_click_times,
            position,
            on_finish=lambda: self.dispatch(self._on_clicker_finished, token),
        )
        if started:
            logger.info(
                "Clicker started (%s ms, %s, %s, count=%s, pos=%s)",
                s.ac_interval_ms, s.ac_button, s.ac_click_type, s.ac_click_times, position,
            )  # fmt: skip
            self._set_mode(Mode.CLICKING)

    def _on_clicker_finished(self, token: object) -> None:
        if token is self._click_token and self.mode is Mode.CLICKING:
            self._set_mode(Mode.IDLE)
            self.toast.show(t("msg_clicker_finished", count=number(self.clicker.clicks_done)), "success")

    def _on_location_change(self, label: str) -> None:
        self._update_setting("ac_location", self._location_lookup[label])
        self._refresh_controls()

    def pick_location(self) -> None:
        if self.mode is not Mode.IDLE or self._picker is not None:
            return
        self._picker = LocationPicker(self, self._on_location_picked)

    def _on_location_picked(self, point: Optional[Tuple[int, int]]) -> None:
        self._picker = None
        if point is None:
            return
        x, y = point
        self.x_entry.set_value(x)
        self.y_entry.set_value(y)
        self.settings.ac_x, self.settings.ac_y = x, y
        self._save()
        self.toast.show(t("msg_position_set", x=x, y=y), "success")

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def _initial_dir(self) -> str:
        last = self.settings.last_macro_dir
        return last if last and os.path.isdir(last) else str(Path.home())

    def _filetypes(self):
        return [(t("filetype_macro"), "*.otm"), (t("filetype_all"), "*.*")]

    def save_macro_dialog(self) -> None:
        if self.mode is not Mode.IDLE or not self.macro.events:
            return
        if not self._commit_inputs(self.loop_entry, self.speed_box):
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title=t("dialog_save_title"),
            defaultextension=".otm",
            initialdir=self._initial_dir(),
            initialfile=self._macro_name or "macro.otm",
            filetypes=self._filetypes(),
        )
        if not path:
            return
        try:
            save_macro(Path(path), self.macro.events, self.settings.macro_loop_count, self.settings.playback_speed)
        except MacroFileError as exc:
            self.toast.show(str(exc), "error", 6000)
            return
        self._macro_name = Path(path).name
        self._update_setting("last_macro_dir", str(Path(path).parent))
        self._refresh_macro_info()
        self.toast.show(t("msg_saved", name=self._macro_name), "success")

    def load_macro_dialog(self) -> None:
        if self.mode is not Mode.IDLE:
            return
        path = filedialog.askopenfilename(
            parent=self, title=t("dialog_open_title"), initialdir=self._initial_dir(), filetypes=self._filetypes()
        )
        if not path:
            return
        try:
            loaded = load_macro(Path(path))
        except MacroFileError as exc:
            self.toast.show(str(exc), "error", 6000)
            return
        self.macro.events = loaded.events
        self._macro_name = Path(path).name
        if loaded.loop_count is not None:
            self.settings.macro_loop_count = max(0, min(LOOPS_MAX, loaded.loop_count))
            self.loop_entry.set_value(self.settings.macro_loop_count)
        if loaded.speed is not None:
            try:
                self.settings.playback_speed = parse_speed(str(loaded.speed))
                self.speed_box.set_value(self.settings.playback_speed)
            except ValueError:
                pass
        self.settings.last_macro_dir = str(Path(path).parent)
        self._save()
        self._refresh_controls()
        key = "msg_opened_legacy" if loaded.legacy else "msg_opened"
        self.toast.show(t(key, name=self._macro_name, count=number(len(loaded.events))), "success", 5000)

    # ------------------------------------------------------------------
    # Window / overlay / tray
    # ------------------------------------------------------------------
    def _on_overlay_toggle(self) -> None:
        self._update_setting("show_overlay", bool(self.overlay_switch.get()))
        if self.settings.show_overlay or self.mode is Mode.COUNTDOWN:
            self.overlay.show()
        else:
            self.overlay.hide()

    def _on_overlay_position(self, label: str) -> None:
        position = self._overlay_lookup[label]
        self._update_setting("overlay_position", position)
        self.overlay.set_position(position)

    def _on_switch(self, name: str, widget: ctk.CTkSwitch) -> None:
        self._update_setting(name, bool(widget.get()))

    def _on_close_request(self) -> None:
        if self.settings.close_to_tray and self.tray.available:
            self.hide_to_tray()
        else:
            self.quit_app()

    def _on_unmap(self, event: tk.Event) -> None:
        if event.widget is self and self.settings.minimize_to_tray and self.tray.available:
            self.after(10, self._hide_if_minimized)

    def _hide_if_minimized(self) -> None:
        if self.state() == "iconic":
            self.hide_to_tray()

    def hide_to_tray(self) -> None:
        self.withdraw()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.notify(t("tray_hint"), APP_NAME)

    def show_window(self) -> None:
        self.deiconify()
        self.state("normal")
        self.lift()
        self.attributes("-topmost", True)
        self.after(50, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def quit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        logger.info("Shutting down")
        self._cancel_countdown()
        for step in (self.hotkeys.shutdown, self.macro.shutdown, self.clicker.shutdown, self.tray.stop):
            try:
                step()
            except Exception:
                logger.exception("Error during shutdown (%s)", getattr(step, "__qualname__", step))
        self._save()
        self.destroy()


def main() -> None:
    setup_logging()
    settings = load_settings()
    if not settings.language:
        settings.language = i18n.detect_system_language()
        save_settings(settings)
    i18n.set_language(settings.language)
    theme.set_font_family(i18n.font_family())

    if not acquire_single_instance("Local\\Otoshi.SingleInstance"):
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, t("already_running"))
        root.destroy()
        return

    set_app_user_model_id("Otoshi.MacroRecorder")
    ctk.set_appearance_mode("dark")
    app = OtoshiApp(settings)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.quit_app()
    finally:
        logging.shutdown()
        lingering = [
            th for th in threading.enumerate() if th is not threading.main_thread() and th.is_alive() and not th.daemon
        ]
        if lingering:  # never leave a zombie process holding global hooks
            os._exit(0)


if __name__ == "__main__":
    main()
