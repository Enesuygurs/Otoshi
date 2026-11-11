"""Otoshi main window (Qt).

Threading model: widgets may only be touched from the GUI thread. Hotkeys and
the engine worker threads post callables through :meth:`MainWindow.dispatch`,
which uses a queued Qt signal to run them on the GUI thread.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, __version__, i18n, theme
from .clicker import AutoClicker
from .config import (
    BUTTONS,
    CLICK_TYPES,
    CLICKER_ACTIONS,
    CLICKS_MAX,
    COORD_LIMIT,
    COUNTDOWN_MAX,
    DEFAULT_HOTKEYS,
    HOLD_MAX_S,
    INTERVAL_MAX_MS,
    INTERVAL_MIN_MS,
    JITTER_PCT_MAX,
    JITTER_PX_MAX,
    LOCATIONS,
    LOOP_DELAY_MAX,
    LOOPS_MAX,
    OVERLAY_POSITIONS,
    SPEED_MAX,
    SPEED_MIN,
    Settings,
    load_settings,
    save_settings,
)
from .hotkeys import (
    ERROR_IN_USE,
    HotkeyManager,
    combo_vks,
    format_hotkey,
    parse_hotkey,
    trigger_for,
    validate_hotkey,
)
from .i18n import number, t
from .logger import logger, setup_logging
from .macro import MacroEngine, MacroFileError, load_macro, save_macro
from .overlay import LocationPicker, StatusOverlay
from .paths import asset, data_dir
from .widgets import (
    Card,
    ElidedLabel,
    PrimaryButton,
    Segmented,
    StatusPill,
    ToggleSwitch,
    app_pixmap,
    combo,
    double_spin,
    glyph_icon,
    label,
    secondary_button,
    section,
    spin,
)
from .winutil import (
    acquire_single_instance,
    open_folder,
    play_finish_sound,
    set_app_user_model_id,
    set_autostart,
    window_rect,
)

ACTIONS = ("record", "play", "clicker")
HOLD_KEY = "hold"  # capture target for the key-hold mode (not a global hotkey)
PAGES = (("macro", "nav_macro", "page_macro_desc", "macro"),
         ("clicker", "nav_clicker", "page_clicker_desc", "cursor"),
         ("settings", "nav_settings", "page_settings_desc", "gear"))  # fmt: skip
HOTKEY_DEBOUNCE_S = 0.25
SIDEBAR_COLLAPSED, SIDEBAR_EXPANDED = 56, 176
CONTENT_WIDTH, MIN_CONTENT_WIDTH = 450, 420


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


def _labels(values, prefix: str):
    return [t(f"{prefix}_{v.replace('-', '_')}") for v in values]


class _Invoker(QObject):
    call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(self._run, Qt.QueuedConnection)

    @staticmethod
    def _run(fn: Callable[[], Any]) -> None:
        try:
            fn()
        except Exception:
            logger.exception("UI callback failed")


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.mode = Mode.IDLE

        self.macro = MacroEngine()
        self.clicker = AutoClicker()
        self.hotkeys = HotkeyManager()

        self._invoker = _Invoker()
        self._play_token: Optional[object] = None
        self._click_token: Optional[object] = None
        self._countdown_left = 0
        self._last_hotkey: Dict[str, float] = {}
        self._capturing: Optional[str] = None
        self._macro_name: Optional[str] = None
        self._tray_hint_shown = False
        self._closing = False
        self._picker: Optional[LocationPicker] = None
        self._page = "macro"
        self._sized = False
        self._tray_color = theme.IDLE

        self._countdown_timer = QTimer(self, interval=1000, timeout=self._countdown_tick)
        self._status_timer = QTimer(self, interval=250, timeout=self._refresh_status)
        self._save_timer = QTimer(self, singleShot=True, interval=300, timeout=self._save)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(asset("icon.ico"))))
        side = SIDEBAR_EXPANDED if settings.sidebar_expanded else SIDEBAR_COLLAPSED
        self.resize(CONTENT_WIDTH + side, 420)
        self.setMinimumSize(MIN_CONTENT_WIDTH + side, 300)

        self.overlay = StatusOverlay(settings.overlay_position)
        self.tray = QSystemTrayIcon(QIcon(app_pixmap(64, theme.IDLE)), self)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self._on_tray_activated)

        self._build_ui()
        self._build_tray_menu()
        self._bind_hotkeys(initial=True)
        if settings.start_with_windows:
            set_autostart(APP_NAME, True)  # refresh the path in case Otoshi was moved
        self._set_mode(Mode.IDLE)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        logger.info("Otoshi %s started (language: %s)", __version__, i18n.language())

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------
    def dispatch(self, fn: Callable[..., Any], *args: Any) -> None:
        """Run ``fn(*args)`` on the GUI thread. Safe to call from any thread."""
        self._invoker.call.emit(lambda: fn(*args))

    def _save(self) -> None:
        save_settings(self.settings)

    def _update_setting(self, name: str, value: Any) -> None:
        setattr(self.settings, name, value)
        self._save_timer.start()

    def _setter(self, name: str, digits: Optional[int] = None) -> Callable[[Any], None]:
        """Callback that stores a control's value in the settings (optionally rounded)."""
        return lambda value: self._update_setting(name, round(value, digits) if digits is not None else value)

    def _alert(self, text: str, retry: bool = True) -> None:
        """Report a problem: a small dialog, or a tray balloon while hidden."""
        if retry:
            logger.warning("Alert: %s", text)
        if retry and not self.isVisible() and not self.tray.isVisible():  # still starting up
            QTimer.singleShot(800, lambda: self._alert(text, retry=False))
        elif self.isVisible() and not self.isMinimized():
            QMessageBox.warning(self, APP_NAME, text)
        elif self.tray.isVisible():
            self.tray.showMessage(APP_NAME, text, QSystemTrayIcon.Warning, 6000)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Content")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        content = QWidget()
        v = self.content_layout = QVBoxLayout(content)
        v.setContentsMargins(18, 0, 12, 0)
        v.setSpacing(0)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        root.addWidget(content, 1)

        # The header scrolls with the page: it is moved into whichever page is shown.
        self.header = QWidget()
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        self.page_title = label("", "PageTitle")
        header.addWidget(self.page_title, 1)
        self.status_pill = StatusPill()
        header.addWidget(self.status_pill)

        self.pages: Dict[str, QWidget] = {}
        self._bodies: Dict[str, QVBoxLayout] = {}
        builders = {"macro": self._build_macro_page, "clicker": self._build_clicker_page,
                    "settings": self._build_settings_page}  # fmt: skip
        for key, _title, _desc, _icon in PAGES:
            scroll, body = self._page_shell()
            builders[key](body)
            body.addStretch(1)
            self.stack.addWidget(scroll)
            self.pages[key] = scroll
            self._bodies[key] = body
        self.setCentralWidget(central)
        self._show_page(self._page)

    def _build_sidebar(self) -> QWidget:
        """Collapsible navigation: an icon rail that expands to show page names."""
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_EXPANDED if self.settings.sidebar_expanded else SIDEBAR_COLLAPSED)
        v = QVBoxLayout(self.sidebar)
        v.setContentsMargins(8, 10, 8, 10)
        v.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.menu_btn = QPushButton()
        self.menu_btn.setObjectName("NavButton")
        self.menu_btn.setFixedSize(40, 40)
        self.menu_btn.setIcon(glyph_icon("menu", theme.MUTED, 18))
        self.menu_btn.setIconSize(QSize(18, 18))
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.clicked.connect(self._toggle_sidebar)
        top.addWidget(self.menu_btn)
        self.brand = label(APP_NAME, "Brand")
        top.addWidget(self.brand, 1)
        v.addLayout(top)
        v.addSpacing(6)

        self.nav_group = QButtonGroup(self.sidebar)
        self.nav_buttons: Dict[str, QPushButton] = {}
        for key, _title, desc, icon in PAGES:
            btn = QPushButton()
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setIcon(glyph_icon(icon, theme.MUTED, 18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(t(desc))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._show_page(k))
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn
            v.addWidget(btn)
        v.addStretch(1)
        self._apply_sidebar_labels(self.settings.sidebar_expanded)
        return self.sidebar

    def _apply_sidebar_labels(self, expanded: bool) -> None:
        self.brand.setVisible(expanded)
        for key, title, _desc, _icon in PAGES:
            self.nav_buttons[key].setText(f"   {t(title)}" if expanded else "")

    def _toggle_sidebar(self) -> None:
        expanded = not self.settings.sidebar_expanded
        self._update_setting("sidebar_expanded", expanded)
        start, end = self.sidebar.width(), SIDEBAR_EXPANDED if expanded else SIDEBAR_COLLAPSED
        if not expanded:
            self._apply_sidebar_labels(False)
        grow_window = not (self.isMaximized() or self.isFullScreen())
        base_width = self.width() - start
        if grow_window:  # keep the content area the same width
            self._apply_min_width(min(start, end))
        anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def step(value: int) -> None:
            self.sidebar.setFixedWidth(value)
            if grow_window:
                self.resize(base_width + value, self.height())

        def done() -> None:
            if expanded:
                self._apply_sidebar_labels(True)
            self._apply_min_width(end)

        anim.valueChanged.connect(step)
        anim.finished.connect(done)
        anim.start(QVariantAnimation.DeleteWhenStopped)

    def _page_shell(self) -> Tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # still scrolls with the wheel
        body = QWidget()
        body.setObjectName("PageBody")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 12, 6, 12)
        v.setSpacing(6)
        scroll.setWidget(body)
        return scroll, v

    def _show_page(self, key: str) -> None:
        if self._capturing:
            self._finish_capture(self._capturing, None)
        self._page = key
        self.page_title.setText(t(next(title for k, title, _d, _i in PAGES if k == key)))
        self.nav_buttons[key].setChecked(True)
        for body in self._bodies.values():
            body.removeWidget(self.header)
        self._bodies[key].insertWidget(0, self.header)
        self.header.show()
        self.stack.setCurrentWidget(self.pages[key])

    def _build_macro_page(self, body: QVBoxLayout) -> None:
        s = self.settings
        body.addWidget(section(t("card_recorder")))
        card = Card()
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.record_btn = PrimaryButton("rose")
        self.record_btn.clicked.connect(self.toggle_recording)
        self.play_btn = PrimaryButton("emerald")
        self.play_btn.clicked.connect(self.toggle_playback)
        buttons.addWidget(self.record_btn)
        buttons.addWidget(self.play_btn)
        v.addLayout(buttons)
        v.addWidget(self._build_macro_panel())
        card.add(panel, (12, 12, 12, 10))
        body.addWidget(card)

        body.addWidget(section(t("card_playback")))
        card = Card()
        self.loop_spin = spin(s.macro_loop_count, 0, LOOPS_MAX, self._setter("macro_loop_count"),
                              special="∞")  # fmt: skip
        card.row(t("row_repeat"), t("hint_repeat_loops"), self.loop_spin)
        self.speed_spin = double_spin(s.playback_speed, SPEED_MIN, SPEED_MAX, self._setter("playback_speed", 2))
        card.row(t("row_speed"), "0.1× – 100×", self.speed_spin)
        self.countdown_spin = spin(
            s.countdown_seconds, 0, COUNTDOWN_MAX, self._setter("countdown_seconds"),
            suffix=" s", special=t("value_off"),
        )  # fmt: skip
        card.row(t("row_countdown"), t("hint_countdown"), self.countdown_spin)
        self.loop_delay_spin = double_spin(
            s.macro_loop_delay_s, 0.0, LOOP_DELAY_MAX, self._setter("macro_loop_delay_s", 2),
            suffix=" s", step=0.5, special=t("value_off"),
        )  # fmt: skip
        card.row(t("row_loop_delay"), t("hint_loop_delay"), self.loop_delay_spin)
        body.addWidget(card)

        body.addWidget(section(t("section_humanize"), t("desc_humanize")))
        card = Card()
        card.row(t("row_humanize_time"), t("hint_humanize_time"),
                 spin(s.humanize_timing_pct, 0, JITTER_PCT_MAX, self._setter("humanize_timing_pct"),
                      suffix=" %", special=t("value_off")))  # fmt: skip
        card.row(t("row_humanize_pos"), t("hint_humanize_pos"),
                 spin(s.humanize_position_px, 0, JITTER_PX_MAX, self._setter("humanize_position_px"),
                      suffix=" px", special=t("value_off")))  # fmt: skip
        body.addWidget(card)

    def _build_macro_panel(self) -> QWidget:
        """Summary of the current macro: status icon, name, stats and file actions."""
        panel = QFrame()
        panel.setObjectName("MacroPanel")
        h = QHBoxLayout(panel)
        h.setContentsMargins(10, 8, 8, 8)
        h.setSpacing(10)
        self.macro_icon = QLabel()
        self.macro_icon.setObjectName("MacroIcon")
        self.macro_icon.setFixedSize(34, 34)
        self.macro_icon.setAlignment(Qt.AlignCenter)
        h.addWidget(self.macro_icon, 0, Qt.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.macro_title = ElidedLabel("", "MacroTitle")
        self.macro_meta = label("", "MacroMeta", wrap=True)
        self.macro_meta.setMinimumWidth(80)  # wrap further instead of widening the page
        text.addWidget(self.macro_title)
        text.addWidget(self.macro_meta)
        h.addLayout(text, 1)
        self.save_btn = secondary_button(t("btn_save"), "save", self.save_macro_dialog)
        self.load_btn = secondary_button(t("btn_open"), "open", self.load_macro_dialog)
        for btn in (self.save_btn, self.load_btn):
            btn.setFixedHeight(30)
            h.addWidget(btn, 0, Qt.AlignVCenter)
        return panel

    def _build_clicker_page(self, body: QVBoxLayout) -> None:
        s = self.settings
        self.clicker_btn = PrimaryButton("violet")
        self.clicker_btn.clicked.connect(self.toggle_clicker)
        body.addWidget(self.clicker_btn)
        card = Card()
        action = Segmented([t("action_mode_click"), t("action_mode_hold")], CLICKER_ACTIONS.index(s.ac_action),
                           self._on_clicker_action)  # fmt: skip
        card.row(t("row_action"), None, action)
        body.addWidget(card)

        # Mouse click mode
        self.click_box = QWidget()
        box = QVBoxLayout(self.click_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        box.addWidget(section(t("card_clicking")))
        card = Card()
        self.interval_spin = spin(
            s.ac_interval_ms, INTERVAL_MIN_MS, INTERVAL_MAX_MS, self._setter("ac_interval_ms"),
            suffix=" ms", width=112,
        )  # fmt: skip
        card.row(t("row_interval"), t("hint_interval"), self.interval_spin)
        self.interval_max_spin = spin(
            s.ac_interval_max_ms, 0, INTERVAL_MAX_MS, self._setter("ac_interval_max_ms"),
            suffix=" ms", special=t("value_off"), width=112,
        )  # fmt: skip
        card.row(t("row_interval_max"), t("hint_interval_max"), self.interval_max_spin)
        self.button_combo = combo(_labels(BUTTONS, "button"), BUTTONS.index(s.ac_button),
                                  lambda i: self._update_setting("ac_button", BUTTONS[i]), width=112)  # fmt: skip
        card.row(t("row_mouse_button"), None, self.button_combo)
        self.type_combo = combo(_labels(CLICK_TYPES, "click"), CLICK_TYPES.index(s.ac_click_type),
                                lambda i: self._update_setting("ac_click_type", CLICK_TYPES[i]), width=112)  # fmt: skip
        card.row(t("row_click_type"), None, self.type_combo)
        self.clicks_spin = spin(s.ac_click_times, 0, CLICKS_MAX, self._setter("ac_click_times"),
                                special="∞", width=112)  # fmt: skip
        card.row(t("row_repeat"), t("hint_repeat_clicks"), self.clicks_spin)
        box.addWidget(card)

        box.addWidget(section(t("card_position")))
        card = Card()
        location = Segmented(_labels(LOCATIONS, "location"), LOCATIONS.index(s.ac_location), self._on_location_change)
        card.row(t("row_click_at"), None, location)
        self.x_spin = spin(s.ac_x, -COORD_LIMIT, COORD_LIMIT, self._setter("ac_x"), width=84)
        self.x_spin.setPrefix("X  ")
        self.y_spin = spin(s.ac_y, -COORD_LIMIT, COORD_LIMIT, self._setter("ac_y"), width=84)
        self.y_spin.setPrefix("Y  ")
        self.pick_btn = secondary_button("", "target", self.pick_location)
        self.pick_btn.setFixedSize(34, 34)
        self.pick_btn.setToolTip(t("picker_title"))
        card.row(t("row_coordinates"), t("hint_coordinates"), self.x_spin, self.y_spin, self.pick_btn)
        box.addWidget(card)
        body.addWidget(self.click_box)

        # Key hold mode
        self.hold_box = QWidget()
        box = QVBoxLayout(self.hold_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        box.addWidget(section(t("card_hold")))
        card = Card()
        self.hold_key_btn = QPushButton()
        self.hold_key_btn.setObjectName("Kbd")
        self.hold_key_btn.setMinimumHeight(26)
        self.hold_key_btn.setCursor(Qt.PointingHandCursor)
        self.hold_key_btn.clicked.connect(lambda: self._begin_capture(HOLD_KEY))
        card.row(t("row_hold_key"), t("hint_hold_key"), self.hold_key_btn)
        self.hold_duration_spin = double_spin(
            s.ac_hold_seconds, 0.0, HOLD_MAX_S, self._setter("ac_hold_seconds", 2),
            suffix=" s", step=0.5, special="∞", width=112,
        )  # fmt: skip
        card.row(t("row_hold_duration"), t("hint_hold_duration"), self.hold_duration_spin)
        box.addWidget(card)
        body.addWidget(self.hold_box)
        self._show_clicker_mode()

    def _build_settings_page(self, body: QVBoxLayout) -> None:
        s = self.settings
        body.addWidget(section(t("section_general")))
        card = Card()
        codes = list(i18n.LANGUAGES)
        self.language_combo = combo(list(i18n.LANGUAGES.values()), codes.index(i18n.language()),
                                    lambda i: self._on_language(codes[i]))  # fmt: skip
        card.row(t("row_language"), t("desc_language"), self.language_combo)
        body.addWidget(card)

        body.addWidget(section(t("card_hotkeys"), t("desc_hotkeys")))
        card = Card()
        self.hotkey_btns: Dict[str, QPushButton] = {}
        for action in ACTIONS:
            btn = QPushButton()
            btn.setObjectName("Kbd")
            btn.setMinimumHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, a=action: self._begin_capture(a))
            self.hotkey_btns[action] = btn
            card.row(t(f"action_{action}"), None, btn)
        body.addWidget(card)

        body.addWidget(section(t("section_overlay")))
        card = Card()
        card.row(t("row_overlay"), t("desc_overlay"), ToggleSwitch(s.show_overlay, self._on_overlay_toggle))
        card.row(t("row_overlay_position"), t("desc_overlay_position"),
                 combo(_labels(OVERLAY_POSITIONS, "position"), OVERLAY_POSITIONS.index(s.overlay_position),
                       self._on_overlay_position))  # fmt: skip
        body.addWidget(card)

        body.addWidget(section(t("section_window")))
        card = Card()
        card.row(t("row_close_to_tray"), t("desc_close_to_tray"),
                 ToggleSwitch(s.close_to_tray, self._setter("close_to_tray")))  # fmt: skip
        card.row(t("row_start_with_windows"), t("desc_start_with_windows"),
                 ToggleSwitch(s.start_with_windows, self._on_autostart))  # fmt: skip
        card.row(t("row_start_in_tray"), t("desc_start_in_tray"),
                 ToggleSwitch(s.start_in_tray, self._setter("start_in_tray")))  # fmt: skip
        body.addWidget(card)

        body.addWidget(section(t("section_notifications")))
        card = Card()
        card.row(t("row_finish_sound"), t("desc_finish_sound"),
                 ToggleSwitch(s.finish_sound, self._setter("finish_sound")))  # fmt: skip
        card.row(t("row_finish_notification"), t("desc_finish_notification"),
                 ToggleSwitch(s.finish_notification, self._setter("finish_notification")))  # fmt: skip
        body.addWidget(card)

        body.addWidget(section(t("section_about")))
        card = Card()
        card.row(t("row_version"), None, label(f"{APP_NAME} {__version__}", "Info"))
        card.row(t("btn_data_folder"), t("desc_data_folder"),
                 secondary_button(t("btn_open"), "folder", lambda: open_folder(data_dir())))  # fmt: skip
        card.row(t("btn_reset_defaults"), None, secondary_button(t("btn_reset_defaults"), None, self._reset_defaults))
        body.addWidget(card)

    def _build_tray_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(t("tray_show"), self.show_window)
        menu.addSeparator()
        menu.addAction(t("action_record"), self.toggle_recording)
        menu.addAction(t("action_play"), self.toggle_playback)
        menu.addAction(t("action_clicker"), self.toggle_clicker)
        menu.addSeparator()
        menu.addAction(t("tray_quit"), self.quit_app)
        old = self.tray.contextMenu()
        self.tray.setContextMenu(menu)
        if old is not None:
            old.deleteLater()

    # ------------------------------------------------------------------
    # Language / defaults
    # ------------------------------------------------------------------
    def _on_language(self, code: str) -> None:
        if code != i18n.language():
            self._update_setting("language", code)
            QTimer.singleShot(0, lambda: self._apply_language(code))  # after the combo's own signal returns

    def _apply_language(self, code: str) -> None:
        if self._capturing:
            self._finish_capture(self._capturing, None)
        i18n.set_language(code)
        theme.set_font_family(i18n.font_family(code))
        QApplication.instance().setStyleSheet(theme.stylesheet(str(asset("chevron-down.png"))))
        QApplication.instance().setFont(QFont(theme.FONT_FAMILY, 10))
        self._build_ui()
        self.overlay.set_font_family(theme.FONT_FAMILY)
        self._build_tray_menu()
        self._set_mode(self.mode)
        logger.info("Language changed to %s", code)

    def _reset_defaults(self) -> None:
        if self.mode is not Mode.IDLE:
            return self._busy()
        keep_language, keep_dir = self.settings.language, self.settings.last_macro_dir
        self.settings.__init__()
        self.settings.language, self.settings.last_macro_dir = keep_language, keep_dir
        self._save()
        self.overlay.set_position(self.settings.overlay_position)
        self._build_ui()
        self._bind_hotkeys()
        self._set_mode(Mode.IDLE)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def _set_mode(self, mode: Mode) -> None:
        self.mode = mode
        self._refresh_controls()
        self._refresh_status()
        if mode is Mode.COUNTDOWN or self.settings.show_overlay:
            self.overlay.show()
        else:
            self.overlay.hide()
        if mode is Mode.IDLE:
            self._status_timer.stop()
        elif not self._status_timer.isActive():
            self._status_timer.start()

    def _status_text(self) -> str:
        if self.mode is Mode.RECORDING:
            return t("status_recording", seconds=f"{self.macro.recording_elapsed:.0f}")
        if self.mode is Mode.COUNTDOWN:
            return t("status_countdown", seconds=self._countdown_left)
        if self.mode is Mode.PLAYING:
            total = self.settings.macro_loop_count
            return t("status_playing", loop=self.macro.current_loop, total=total if total else "∞")
        if self.mode is Mode.CLICKING:
            if self.settings.ac_action == "hold":
                return t("status_holding", key=format_hotkey(self.settings.ac_hold_key))
            return t("status_clicking", count=number(self.clicker.clicks_done))
        if self.macro.events:
            return f"{t('status_macro_ready')} · {t('info_events', count=number(len(self.macro.events)))}"
        return t(MODE_STYLE[Mode.IDLE][0])

    def _status_color(self) -> str:
        if self.mode is Mode.IDLE and self.macro.events:
            return theme.EMERALD  # a recorded / loaded macro is waiting to be played
        return MODE_STYLE[self.mode][1]

    def _refresh_status(self) -> None:
        text, color = self._status_text(), self._status_color()
        self.status_pill.set(text, color)
        self.overlay.set_status(text, color)
        self.tray.setToolTip(f"{APP_NAME}: {text}")
        if color != self._tray_color:  # redraw the icon only when it changes
            self._tray_color = color
            self.tray.setIcon(QIcon(app_pixmap(64, color)))

    def _refresh_controls(self) -> None:
        mode, s = self.mode, self.settings
        idle = mode is Mode.IDLE
        has_macro = bool(self.macro.events)

        def caption(key: str, action: str, **kw: Any) -> str:
            return f"{t(key, **kw)}   ·   {format_hotkey(s.hotkey(action))}"

        def setup(btn: PrimaryButton, text: str, icon: str, variant: str, enabled: bool) -> None:
            btn.setText(text)
            btn.setIcon(glyph_icon(icon, "#FFFFFF", 18))
            btn.set_variant(variant)
            btn.setEnabled(enabled)

        if mode is Mode.RECORDING:
            setup(self.record_btn, caption("btn_stop_recording", "record"), "stop", "rose", True)
        else:
            setup(self.record_btn, caption("btn_record", "record"), "record", "rose", idle)

        if mode is Mode.PLAYING:
            setup(self.play_btn, caption("btn_stop_playback", "play"), "stop", "emerald", True)
        elif mode is Mode.COUNTDOWN:
            setup(self.play_btn, caption("btn_cancel_countdown", "play", seconds=self._countdown_left), "stop", "amber",
                  True)  # fmt: skip
        else:
            setup(self.play_btn, caption("btn_play", "play"), "play", "emerald", idle and has_macro)

        hold = s.ac_action == "hold"
        if mode is Mode.CLICKING:
            stop_key = "btn_stop_holding" if hold else "btn_stop_clicking"
            setup(self.clicker_btn, caption(stop_key, "clicker"), "stop", "violet", True)
        else:
            start_key = "btn_start_holding" if hold else "btn_start_clicking"
            setup(self.clicker_btn, caption(start_key, "clicker"), "play" if hold else "cursor", "violet", idle)
        if self._capturing != HOLD_KEY:
            self.hold_key_btn.setText(format_hotkey(s.ac_hold_key))
            self._set_capturing_style(self.hold_key_btn, False)
            self.hold_key_btn.setEnabled(idle)

        self.save_btn.setEnabled(idle and has_macro)
        self.load_btn.setEnabled(idle)
        for action, btn in self.hotkey_btns.items():
            if self._capturing != action:
                btn.setText(format_hotkey(s.hotkey(action)))
                self._set_capturing_style(btn, False)
                btn.setEnabled(idle)
        fixed = s.ac_location == "fixed"
        for widget in (self.x_spin, self.y_spin, self.pick_btn):
            widget.setEnabled(fixed and idle)
        self._refresh_macro_info()

    @staticmethod
    def _set_capturing_style(btn: QPushButton, on: bool) -> None:
        if bool(btn.property("capturing")) != on:
            btn.setProperty("capturing", on)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _refresh_macro_info(self) -> None:
        events = self.macro.events
        if self.mode is Mode.RECORDING:
            icon, color = "record", theme.ROSE
            title, meta = t("mode_recording"), t("info_recording")
        elif not events:
            icon, color = "macro", theme.DIM
            title = t("macro_none")
            meta = t("macro_hint", hotkey=format_hotkey(self.settings.record_hotkey))
        else:
            icon, color = "macro", theme.EMERALD
            title = self._macro_name or t("macro_unsaved")
            meta = f"{t('info_events', count=number(len(events)))}   ·   {_fmt_duration(self.macro.duration)}"
        dpr = self.devicePixelRatioF()
        pixmap = glyph_icon(icon, color, 16).pixmap(QSize(16, 16), dpr)
        self.macro_icon.setPixmap(pixmap)
        self.macro_title.setText(title)
        self.macro_meta.setText(meta)

    def _busy(self) -> None:
        """Another mode is running; the status indicator already shows which."""

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------
    def _bind_hotkeys(self, initial: bool = False) -> None:
        if initial:
            for action in ACTIONS:
                error = validate_hotkey(self.settings.hotkey(action))
                if error:
                    logger.warning("Invalid %s hotkey %r (%s)", action, self.settings.hotkey(action), error)
                    self.settings.set_hotkey(action, DEFAULT_HOTKEYS[action])
            if len({self.settings.hotkey(a) for a in ACTIONS}) < len(ACTIONS):
                for action in ACTIONS:
                    self.settings.set_hotkey(action, DEFAULT_HOTKEYS[action])
            self._save()

        bindings = {a: (self.settings.hotkey(a), (lambda a=a: self.dispatch(self._on_hotkey, a))) for a in ACTIONS}
        errors = self.hotkeys.bind(bindings)
        if errors:
            names = ", ".join(format_hotkey(self.settings.hotkey(a)) for a in errors)
            in_use = len(errors) == 1 and ERROR_IN_USE in errors.values()
            self._alert(t("hk_err_in_use", hotkey=names) if in_use else t("msg_hotkeys_failed", hotkeys=names))

    def _on_hotkey(self, action: str) -> None:
        now = time.monotonic()
        if now - self._last_hotkey.get(action, 0.0) < HOTKEY_DEBOUNCE_S:
            return
        self._last_hotkey[action] = now
        {"record": self.toggle_recording, "play": self.toggle_playback, "clicker": self.toggle_clicker}[action]()

    def _begin_capture(self, action: str) -> None:
        if self._capturing == action:
            return self._finish_capture(action, None)
        if self._capturing:
            self._finish_capture(self._capturing, None)
        if self.mode is not Mode.IDLE:
            return self._busy()
        self._capturing = action
        self.hotkeys.unbind_all()  # so pressing F2 now does not start a recording
        btn = self.hold_key_btn if action == HOLD_KEY else self.hotkey_btns[action]
        btn.setText(t("press_keys"))
        self._set_capturing_style(btn, True)
        self.hotkeys.capture(lambda result: self.dispatch(self._finish_capture, action, result))

    def _finish_capture(self, action: str, result: Optional[str]) -> None:
        if self._capturing != action:
            return
        self._capturing = None
        self.hotkeys.cancel_capture()
        if result is None:
            pass
        elif action == HOLD_KEY:
            self._set_hold_key(result)
        else:
            error = validate_hotkey(result)
            clash = next((a for a in ACTIONS if a != action and self.settings.hotkey(a) == result), None)
            if error:
                self._alert(error)
            elif clash:
                self._alert(t("msg_hotkey_clash", hotkey=format_hotkey(result), action=t(f"action_{clash}")))
            else:
                self.settings.set_hotkey(action, result)
                self._save()
        self._bind_hotkeys()
        self._refresh_controls()

    def _set_hold_key(self, combo: str) -> None:
        if parse_hotkey(combo) is None:
            self._alert(t("hk_err_unsupported", key=format_hotkey(combo)))
        elif combo in (self.settings.hotkey(a) for a in ACTIONS):
            self._alert(t("msg_hold_key_is_hotkey", hotkey=format_hotkey(combo)))
        else:
            self._update_setting("ac_hold_key", combo)

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
            return self._alert(t("msg_record_failed"))
        logger.info("Recording started")
        self._set_mode(Mode.RECORDING)

    def _stop_recording(self) -> None:
        rect = window_rect(int(self.winId())) if self.isVisible() and not self.isMinimized() else None
        count = self.macro.stop_recording(exclude_rect=rect)
        logger.info("Recording stopped: %d events", count)
        if count:
            self._macro_name = None
        self._set_mode(Mode.IDLE)

    def toggle_playback(self) -> None:
        if self.mode is Mode.PLAYING:
            self.macro.stop_playback()
            self._set_mode(Mode.IDLE)
        elif self.mode is Mode.COUNTDOWN:
            self._countdown_timer.stop()
            self._set_mode(Mode.IDLE)
        elif self.mode is Mode.IDLE:
            self._request_playback()
        else:
            self._busy()

    def _request_playback(self) -> None:
        if not self.macro.events:
            return self._alert(t("msg_no_macro"))
        for box in (self.loop_spin, self.speed_spin, self.countdown_spin, self.loop_delay_spin):
            box.interpretText()
        if self.settings.countdown_seconds <= 0:
            return self._start_playback()
        self._countdown_left = self.settings.countdown_seconds
        self._set_mode(Mode.COUNTDOWN)
        self._countdown_timer.start()

    def _countdown_tick(self) -> None:
        if self.mode is not Mode.COUNTDOWN:
            return self._countdown_timer.stop()
        self._countdown_left -= 1
        if self._countdown_left <= 0:
            self._countdown_timer.stop()
            return self._start_playback()
        self._refresh_controls()
        self._refresh_status()

    def _start_playback(self) -> None:
        token = object()
        self._play_token = token
        s = self.settings
        started = self.macro.play(
            s.macro_loop_count,
            s.playback_speed,
            on_finish=lambda: self.dispatch(self._on_playback_finished, token),
            loop_delay=s.macro_loop_delay_s,
            timing_jitter=s.humanize_timing_pct / 100.0,
            position_jitter=s.humanize_position_px,
        )
        if started:
            logger.info("Playback started (loops=%s, speed=%s)", s.macro_loop_count, s.playback_speed)
        self._set_mode(Mode.PLAYING if started else Mode.IDLE)

    def _on_playback_finished(self, token: object) -> None:
        if token is self._play_token and self.mode is Mode.PLAYING:
            self._set_mode(Mode.IDLE)
            self._notify_finished(t("msg_playback_finished"))

    # ------------------------------------------------------------------
    # Auto clicker
    # ------------------------------------------------------------------
    def toggle_clicker(self) -> None:
        if self.mode is Mode.CLICKING:
            self.clicker.stop()
            self._set_mode(Mode.IDLE)
        elif self.mode is Mode.IDLE:
            self._start_clicker()
        else:
            self._busy()

    def _start_clicker(self) -> None:
        s = self.settings
        token = object()
        self._click_token = token
        on_finish = lambda: self.dispatch(self._on_clicker_finished, token)  # noqa: E731
        if s.ac_action == "hold":
            self.hold_duration_spin.interpretText()
            vks = combo_vks(s.ac_hold_key)
            if not vks:
                return self._alert(t("msg_hold_no_key"))
            if s.ac_hold_key in (s.hotkey(a) for a in ACTIONS):
                return self._alert(t("msg_hold_key_is_hotkey", hotkey=format_hotkey(s.ac_hold_key)))
            started = self.clicker.start_hold(vks, s.ac_hold_seconds, on_finish=on_finish)
            if started:
                logger.info("Key hold started (%s, %s s)", s.ac_hold_key, s.ac_hold_seconds)
        else:
            for box in (self.interval_spin, self.interval_max_spin, self.clicks_spin, self.x_spin, self.y_spin):
                box.interpretText()
            position = (s.ac_x, s.ac_y) if s.ac_location == "fixed" else None
            started = self.clicker.start(
                s.ac_interval_ms, s.ac_button, s.ac_click_type, s.ac_click_times, position,
                on_finish=on_finish, interval_max_ms=s.ac_interval_max_ms,
            )  # fmt: skip
            if started:
                logger.info("Clicker started (%s-%s ms, %s, %s, count=%s, pos=%s)", s.ac_interval_ms,
                            s.ac_interval_max_ms, s.ac_button, s.ac_click_type, s.ac_click_times, position)  # fmt: skip
        if started:
            self._set_mode(Mode.CLICKING)

    def _on_clicker_finished(self, token: object) -> None:
        if token is self._click_token and self.mode is Mode.CLICKING:
            self._set_mode(Mode.IDLE)
            if self.settings.ac_action == "hold":
                message = t("msg_hold_finished")
            else:
                message = t("msg_clicker_finished", count=number(self.clicker.clicks_done))
            self._notify_finished(message)

    def _on_clicker_action(self, index: int) -> None:
        self._update_setting("ac_action", CLICKER_ACTIONS[index])
        self._show_clicker_mode()
        self._refresh_controls()

    def _show_clicker_mode(self) -> None:
        hold = self.settings.ac_action == "hold"
        self.click_box.setVisible(not hold)
        self.hold_box.setVisible(hold)

    def _notify_finished(self, message: str) -> None:
        if self.settings.finish_sound:
            play_finish_sound()
        if self.settings.finish_notification and self.tray.isVisible():
            self.tray.showMessage(APP_NAME, message, QIcon(app_pixmap(64)), 4000)

    def _on_autostart(self, on: bool) -> None:
        if set_autostart(APP_NAME, on):
            self._update_setting("start_with_windows", on)
        else:
            self._alert(t("msg_autostart_failed"))

    def _on_location_change(self, index: int) -> None:
        self._update_setting("ac_location", LOCATIONS[index])
        self._refresh_controls()

    def pick_location(self) -> None:
        if self.mode is not Mode.IDLE or self._picker is not None:
            return
        self._picker = LocationPicker(self._on_location_picked)
        self._picker.start()

    def _on_location_picked(self, point: Optional[Tuple[int, int]]) -> None:
        self._picker = None
        self.activateWindow()
        if point is None:
            return
        x, y = point
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def _initial_dir(self) -> str:
        last = self.settings.last_macro_dir
        return last if last and os.path.isdir(last) else str(Path.home())

    def _filter(self) -> str:
        return f"{t('filetype_macro')} (*.otm);;{t('filetype_all')} (*.*)"

    def save_macro_dialog(self) -> None:
        if self.mode is not Mode.IDLE or not self.macro.events:
            return
        start = os.path.join(self._initial_dir(), self._macro_name or "macro.otm")
        path, _ = QFileDialog.getSaveFileName(self, t("dialog_save_title"), start, self._filter())
        if not path:
            return
        if not path.lower().endswith(".otm"):
            path += ".otm"
        try:
            save_macro(Path(path), self.macro.events, self.settings.macro_loop_count, self.settings.playback_speed)
        except MacroFileError as exc:
            return self._alert(str(exc))
        self._macro_name = Path(path).name
        self._update_setting("last_macro_dir", str(Path(path).parent))
        self._refresh_macro_info()

    def load_macro_dialog(self) -> None:
        if self.mode is not Mode.IDLE:
            return
        path, _ = QFileDialog.getOpenFileName(self, t("dialog_open_title"), self._initial_dir(), self._filter())
        if not path:
            return
        try:
            loaded = load_macro(Path(path))
        except MacroFileError as exc:
            return self._alert(str(exc))
        self.macro.events = loaded.events
        self._macro_name = Path(path).name
        if loaded.loop_count is not None:
            self.loop_spin.setValue(max(0, min(LOOPS_MAX, loaded.loop_count)))
        if loaded.speed is not None:
            self.speed_spin.setValue(max(SPEED_MIN, min(SPEED_MAX, loaded.speed)))
        self._update_setting("last_macro_dir", str(Path(path).parent))
        self._refresh_controls()
        self._refresh_status()

    # ------------------------------------------------------------------
    # Window / overlay / tray
    # ------------------------------------------------------------------
    def _on_overlay_toggle(self, on: bool) -> None:
        self._update_setting("show_overlay", on)
        self._set_mode(self.mode)

    def _on_overlay_position(self, index: int) -> None:
        self._update_setting("overlay_position", OVERLAY_POSITIONS[index])
        self.overlay.set_position(OVERLAY_POSITIONS[index])

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def closeEvent(self, event) -> None:
        if not self._closing and self.settings.close_to_tray and self.tray.isVisible():
            event.ignore()
            self.hide_to_tray()
            return
        self.quit_app()
        event.accept()

    def _min_content_width(self) -> int:
        """Narrowest content area in which no page overflows its viewport.

        Pages scroll vertically only, so anything wider than the viewport
        would be cut off; this grows with long translations and large fonts.
        """
        margins = self.content_layout.contentsMargins()
        needed = max(page.widget().minimumSizeHint().width() for page in self.pages.values())
        return max(MIN_CONTENT_WIDTH, needed + margins.left() + margins.right())

    def _apply_min_width(self, sidebar_width: int) -> None:
        self.setMinimumWidth(self._min_content_width() + sidebar_width)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._sized:  # style sheet metrics are only final once shown
            self._sized = True
            self._apply_min_width(self.sidebar.width())
            self._fit_height()
            QTimer.singleShot(0, self._fit_height)  # again once wrapped labels have settled

    def _fit_height(self) -> None:
        """Open tall enough to show the whole macro page (and so the clicker page) without scrolling."""
        page = self.pages["macro"]
        body = page.widget().layout()
        self.centralWidget().layout().activate()
        body.activate()
        top = page.viewport().mapTo(self, QPoint(0, 0)).y()
        width = page.viewport().width()
        needed = top + (body.totalHeightForWidth(width) if body.hasHeightForWidth() else body.totalSizeHint().height())
        frame = self.frameGeometry().height() - self.height()
        screen = self.screen().availableGeometry().height() - frame if self.screen() else needed
        self.resize(self.width(), max(self.minimumHeight(), min(needed, screen)))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        # Minimising always hides to the tray (when a tray is available).
        if event.type() == event.Type.WindowStateChange and self.isMinimized() and self.tray.isVisible():
            QTimer.singleShot(0, self.hide_to_tray)

    def hide_to_tray(self) -> None:
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(APP_NAME, t("tray_hint"), QIcon(app_pixmap(64)), 3000)

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        logger.info("Shutting down")
        self._countdown_timer.stop()
        self._status_timer.stop()
        for step in (self.hotkeys.shutdown, self.macro.shutdown, self.clicker.shutdown):
            try:
                step()
            except Exception:
                logger.exception("Error during shutdown (%s)", getattr(step, "__qualname__", step))
        self._save_timer.stop()
        self._save()
        self.tray.hide()
        self.overlay.close()
        QApplication.instance().quit()


def main() -> None:
    setup_logging()
    settings = load_settings()
    if not settings.language:
        settings.language = i18n.detect_system_language()
        save_settings(settings)
    i18n.set_language(settings.language)
    theme.set_font_family(i18n.font_family())

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # the tray keeps the app alive
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)  # dark title bar (Qt 6.8+)
    except AttributeError:
        pass

    if not acquire_single_instance("Local\\Otoshi.SingleInstance"):
        QMessageBox.information(None, APP_NAME, t("already_running"))
        return

    set_app_user_model_id("Otoshi.MacroRecorder")
    app.setStyle("Fusion")
    app.setFont(QFont(theme.FONT_FAMILY, 10))
    app.setStyleSheet(theme.stylesheet(str(asset("chevron-down.png"))))
    window = MainWindow(settings)
    if not (settings.start_in_tray and QSystemTrayIcon.isSystemTrayAvailable()):
        window.show()
    code = app.exec()
    logging.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
