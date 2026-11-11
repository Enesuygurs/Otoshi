"""Always-on-top helper windows: the status overlay and the location picker."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .i18n import t
from .winutil import cursor_pos


class StatusOverlay(QWidget):
    """Small, click-through, anti-aliased pill in a screen corner."""

    MARGIN = 16

    def __init__(self, position: str = "top-left") -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._position = position
        self._text, self._color = "", theme.IDLE
        self._font = QFont(theme.FONT_FAMILY, 9)
        self._font.setWeight(QFont.DemiBold)
        self.set_status(t("mode_ready"), theme.IDLE)

    def set_font_family(self, family: str) -> None:
        self._font.setFamily(family)
        self._resize()

    def set_status(self, text: str, color: str) -> None:
        if (text, color) == (self._text, self._color):
            return
        self._text, self._color = text, color
        self._resize()
        self.update()

    def set_position(self, position: str) -> None:
        self._position = position
        self._place()

    def _resize(self) -> None:
        fm = QFontMetrics(self._font)
        h = fm.height() + 14
        w = 30 + fm.horizontalAdvance(self._text) + 16
        self.setFixedSize(w, h)
        self._place()

    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        m = self.MARGIN
        x = area.left() + m if "left" in self._position else area.right() - self.width() - m
        y = area.top() + m if "top" in self._position else area.bottom() - self.height() - m
        self.move(x, y)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        bg = QColor(theme.SURFACE)
        bg.setAlpha(240)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._color))
        p.drawEllipse(QRectF(14, self.height() / 2 - 4, 8, 8))
        p.setPen(QColor(theme.TEXT))
        p.setFont(self._font)
        p.drawText(QRect(30, 0, self.width() - 30, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self._text)


class LocationPicker(QWidget):
    """Dims every monitor and reports the physical screen position of the next click.

    Esc or right-click cancels. ``on_done`` receives ``(x, y)`` or ``None``.
    """

    def __init__(self, on_done: Callable[[Optional[Tuple[int, int]]], None]) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self._on_done = on_done
        self._finished = False
        self._coords = ""
        screens = QGuiApplication.screens()
        area = screens[0].geometry()
        for screen in screens[1:]:
            area = area.united(screen.geometry())
        self.setGeometry(area)
        self._primary = QGuiApplication.primaryScreen().geometry()
        self._title_font = QFont(theme.FONT_FAMILY, 11)
        self._title_font.setWeight(QFont.DemiBold)
        self._body_font = QFont(theme.FONT_FAMILY, 9)

    def start(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 95))
        w, h = 360, 92
        top_left = self.mapFromGlobal(QPoint(self._primary.center().x() - w // 2, self._primary.top() + 40))
        box = QRectF(top_left.x(), top_left.y(), w, h)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor(theme.SURFACE))
        p.drawRoundedRect(box, 12, 12)
        p.setPen(QColor(theme.TEXT))
        p.setFont(self._title_font)
        p.drawText(box.adjusted(0, 10, 0, -h + 38), Qt.AlignCenter, t("picker_title"))
        p.setPen(QColor(theme.VIOLET))
        p.drawText(box.adjusted(0, 36, 0, -h + 62), Qt.AlignCenter, self._coords)
        p.setPen(QColor(theme.DIM))
        p.setFont(self._body_font)
        p.drawText(box.adjusted(0, 62, 0, -6), Qt.AlignCenter, t("picker_cancel"))

    def mouseMoveEvent(self, _event) -> None:
        pos = cursor_pos()
        if pos:
            self._coords = f"X {pos[0]}    Y {pos[1]}"
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            pos = cursor_pos()
            if pos is None:
                g = event.globalPosition().toPoint()
                pos = (g.x(), g.y())
            self._finish(pos)
        else:
            self._finish(None)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._finish(None)

    def _finish(self, result: Optional[Tuple[int, int]]) -> None:
        if self._finished:
            return
        self._finished = True
        self.releaseKeyboard()
        self.close()
        self._on_done(result)
