"""Reusable Qt building blocks with the Otoshi look (styled by ``theme.stylesheet``)."""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Callable, List, Optional, Sequence

from PIL import Image
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QValidator
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .i18n import upper
from .paths import asset

# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue(), "PNG")
    return pixmap


@lru_cache(maxsize=128)
def glyph_icon(name: str, color: str = theme.TEXT, size: int = 18) -> QIcon:
    icon = QIcon(pil_to_pixmap(icons.glyph(name, color, size * 3)))
    icon.addPixmap(pil_to_pixmap(icons.glyph(name, theme.DIM, size * 3)), QIcon.Disabled)
    return icon


@lru_cache(maxsize=16)
def app_pixmap(size: int, dot: str = theme.BRAND) -> QPixmap:
    """App mark from the pre-rendered assets (rendering it live costs ~0.25 s)."""
    name = next((n for n, c in theme.ICON_VARIANTS.items() if c == dot), None)
    path = asset(f"app-{name}.png") if name else None
    pixmap = QPixmap(str(path)) if path and path.exists() else pil_to_pixmap(icons.app_icon(128, dot))
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFixedHeight(1)
    return line


class Card(QFrame):
    """Rounded surface holding rows separated by hairlines."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(0)
        self._rows = 0

    def add(self, widget: QWidget, margins=(18, 12, 18, 12)) -> QWidget:
        if self._rows:
            holder = QWidget()
            lay = QHBoxLayout(holder)
            lay.setContentsMargins(18, 0, 18, 0)
            lay.addWidget(separator())
            self._layout.addWidget(holder)
        wrapper = QWidget()
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(*margins)
        lay.addWidget(widget)
        self._layout.addWidget(wrapper)
        self._rows += 1
        return widget

    def row(self, title: str, desc: Optional[str], *controls: QWidget) -> QWidget:
        """Title/description on the left, controls aligned right."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "RowTitle"))
        if desc:
            text.addWidget(label(desc, "RowDesc", wrap=True))
        h.addLayout(text, 1)
        for control in controls:
            h.addWidget(control, 0, Qt.AlignVCenter)
        return self.add(row)


def section(title: str, desc: Optional[str] = None) -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 14, 0, 6)
    v.setSpacing(2)
    v.addWidget(label(upper(title), "SectionTitle"))
    if desc:
        v.addWidget(label(desc, "SectionDesc", wrap=True))
    return box


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class PrimaryButton(QPushButton):
    def __init__(self, variant: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Primary")
        self.setMinimumHeight(46)
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._variant = ""
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        if variant != self._variant:
            self._variant = variant
            self.setProperty("variant", variant)
            self.style().unpolish(self)
            self.style().polish(self)


def secondary_button(text: str, icon: Optional[str] = None, on_click: Optional[Callable] = None) -> QPushButton:
    btn = QPushButton(f"  {text}" if icon and text else text)
    btn.setObjectName("Secondary")
    btn.setMinimumHeight(34)
    btn.setCursor(Qt.PointingHandCursor)
    if icon:
        btn.setIcon(glyph_icon(icon, theme.TEXT, 16))
        btn.setIconSize(QSize(16, 16))
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def combo(values: Sequence[str], current: int, on_change: Callable[[int], None], width: int = 180) -> QComboBox:
    box = QComboBox()
    box.addItems(list(values))
    box.setCurrentIndex(current)
    box.setFixedWidth(width)
    box.setCursor(Qt.PointingHandCursor)
    box.currentIndexChanged.connect(on_change)
    return box


def spin(
    value: int,
    lo: int,
    hi: int,
    on_change: Callable[[int], None],
    suffix: str = "",
    special: str = "",
    width: int = 120,
) -> QSpinBox:
    box = QSpinBox()
    box.setRange(lo, hi)
    box.setValue(value)
    box.setSuffix(suffix)
    if special:
        box.setSpecialValueText(special)
    box.setButtonSymbols(QAbstractSpinBox.NoButtons)
    box.setAlignment(Qt.AlignCenter)
    box.setFixedWidth(width)
    box.valueChanged.connect(on_change)
    return box


class SpeedSpin(QDoubleSpinBox):
    """Shows ``1.5×`` rather than the locale's ``1,50×``."""

    def textFromValue(self, value: float) -> str:
        return f"{value:g}"

    def valueFromText(self, text: str) -> float:
        try:
            return float(text.replace(self.suffix(), "").replace(",", ".").strip())
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):
        body = text.replace(self.suffix(), "").replace(",", ".").strip()
        try:
            value = float(body)
        except ValueError:
            return (QValidator.Intermediate if body in ("", ".") else QValidator.Invalid), text, pos
        state = QValidator.Acceptable if self.minimum() <= value <= self.maximum() else QValidator.Intermediate
        return state, text, pos


def double_spin(value: float, lo: float, hi: float, on_change: Callable[[float], None], width: int = 120):
    box = SpeedSpin()
    box.setRange(lo, hi)
    box.setDecimals(2)
    box.setSingleStep(0.25)
    box.setValue(value)
    box.setSuffix("×")
    box.setButtonSymbols(QAbstractSpinBox.NoButtons)
    box.setAlignment(Qt.AlignCenter)
    box.setFixedWidth(width)
    box.valueChanged.connect(on_change)
    return box


class Segmented(QFrame):
    """Pill-shaped group of mutually exclusive options."""

    def __init__(self, labels: List[str], current: int, on_change: Callable[[int], None]) -> None:
        super().__init__()
        self.setObjectName("Segment")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self._group = QButtonGroup(self)
        for i, text in enumerate(labels):
            btn = QPushButton(text)
            btn.setObjectName("SegmentButton")
            btn.setCheckable(True)
            btn.setMinimumHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            self._group.addButton(btn, i)
            h.addWidget(btn)
        self._group.button(current).setChecked(True)
        self._group.idClicked.connect(on_change)


class ToggleSwitch(QAbstractButton):
    """Animated, anti-aliased on/off switch."""

    def __init__(self, checked: bool, on_toggle: Callable[[bool], None]) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._start)
        self.toggled.connect(on_toggle)

    def _get(self) -> float:
        return self._offset

    def _set(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get, _set)

    def _start(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        off, on = QColor("#3A3A42"), QColor(theme.BLUE)
        k = self._offset
        track = QColor(
            round(off.red() + (on.red() - off.red()) * k),
            round(off.green() + (on.green() - off.green()) * k),
            round(off.blue() + (on.blue() - off.blue()) * k),
        )
        if self.underMouse():
            track = track.lighter(115)
        r = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = self.height() - 6
        x = 3 + k * (self.width() - d - 6)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, 3, d, d))

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class StatusPill(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Pill")
        self.setFixedHeight(30)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 0, 14, 0)
        h.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self._text = label("", "PillText")
        h.addWidget(self._dot)
        h.addWidget(self._text, 1)
        self._color = ""

    def set(self, text: str, color: str) -> None:
        if color != self._color:
            self._color = color
            self._dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self._text.setText(text)


class Toast(QLabel):
    """One-line feedback message that falls back to an idle hint."""

    def __init__(self, idle_text: str) -> None:
        super().__init__(idle_text)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self._idle = idle_text
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear_message)

    def show_message(self, text: str, level: str = "info", duration_ms: int = 3500) -> None:
        self.setText(text)
        self.setStyleSheet(f"color: {theme.LEVEL_COLORS.get(level, theme.MUTED)};")
        self._timer.start(duration_ms)

    def clear_message(self) -> None:
        self._timer.stop()
        self.setText(self._idle)
        self.setStyleSheet("")
