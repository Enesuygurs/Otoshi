"""Every page must fit its viewport: the horizontal scrollbar is off, so any
overflow would silently cut off the right edge of the content."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from otoshi import i18n, theme  # noqa: E402
from otoshi.app import MainWindow  # noqa: E402
from otoshi.config import Settings  # noqa: E402
from otoshi.paths import asset  # noqa: E402

LANGUAGES = ["en", "tr", "de", "es", "fr", "it", "pt", "ru", "ja", "zh"]
# Hotkeys nobody uses, so the window never grabs the user's own shortcuts.
HOTKEYS = dict(
    record_hotkey="ctrl+alt+shift+f21", play_hotkey="ctrl+alt+shift+f22", clicker_hotkey="ctrl+alt+shift+f23"
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setFont(QFont(theme.FONT_FAMILY, 9))
    app.setStyleSheet(theme.stylesheet(str(asset("chevron-down.png"))))
    return app


def clipped_widgets(window: MainWindow, app: QApplication):
    found = []
    for key, page in window.pages.items():
        window._show_page(key)
        app.processEvents()
        viewport = page.viewport()
        right = viewport.mapToGlobal(QPoint(viewport.width(), 0)).x()
        for child in page.widget().findChildren(QWidget):
            if child.isVisibleTo(page.widget()) and child.width():
                overflow = child.mapToGlobal(QPoint(child.width(), 0)).x() - right
                if overflow > 1:
                    found.append(f"{key}: {type(child).__name__}#{child.objectName()} +{overflow}px")
    return found


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("expanded", [False, True], ids=["collapsed", "expanded"])
@pytest.mark.parametrize("with_macro", [False, True], ids=["empty", "macro"])
def test_pages_fit_at_minimum_width(qapp, language, expanded, with_macro):
    i18n.set_language(language)
    window = MainWindow(Settings(language=language, sidebar_expanded=expanded, **HOTKEYS))
    try:
        window.show()
        window.resize(window.minimumSize())
        if with_macro:
            window.macro.events = [{"t": i * 0.02, "type": "move", "x": i, "y": i} for i in range(48)]
            window._macro_name = "a-very-long-macro-file-name-without-any-spaces-at-all-2026"
        window._refresh_controls()
        assert clipped_widgets(window, qapp) == []
    finally:
        window.quit_app()
        window.deleteLater()
        i18n.set_language("en")


def test_status_shows_recorded_macro(qapp):
    i18n.set_language("en")
    window = MainWindow(Settings(language="en", **HOTKEYS))
    try:
        assert window.status_pill._text.text() == "Ready"
        window.macro.events = [{"t": i * 0.02, "type": "move", "x": i, "y": i} for i in range(48)]
        window._set_mode(window.mode)  # what happens when a recording stops
        assert window.status_pill._text.text() == "Macro ready · 48 events"
        assert window.overlay._text == "Macro ready · 48 events"
        assert window._status_color() == theme.EMERALD
    finally:
        window.quit_app()
        window.deleteLater()


def test_pages_have_no_scrollbars(qapp):
    window = MainWindow(Settings(language="en", **HOTKEYS))
    try:
        for page in window.pages.values():
            assert page.verticalScrollBarPolicy() == page.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    finally:
        window.quit_app()
        window.deleteLater()


def test_header_scrolls_with_each_page(qapp):
    window = MainWindow(Settings(language="en", **HOTKEYS))
    try:
        window.show()
        for key, page in window.pages.items():
            window._show_page(key)
            qapp.processEvents()
            assert window.header.parentWidget() is page.widget()  # inside the scrolled body, not fixed above it
            assert window.header.isVisible() and window.header.y() < 40
    finally:
        window.quit_app()
        window.deleteLater()


def test_window_opens_tall_enough_for_macro_and_clicker_pages(qapp):
    window = MainWindow(Settings(language="en", **HOTKEYS))
    try:
        window.show()
        qapp.processEvents()
        screen_limited = window.frameGeometry().height() >= window.screen().availableGeometry().height()
        for key in ("macro", "clicker"):
            window._show_page(key)
            qapp.processEvents()
            assert window.pages[key].verticalScrollBar().maximum() == 0 or screen_limited, key
    finally:
        window.quit_app()
        window.deleteLater()
