"""Reusable Qt building blocks with the Otoshi look (styled by ``theme.stylesheet``)."""

from __future__ import annotations

import io
import re
from functools import lru_cache
from typing import Callable, List, Optional, Sequence

from PIL import Image
from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap, QValidator
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
    QStyle,
    QStyleOptionButton,
    QStylePainter,
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


class ElidedLabel(QLabel):
    """Single-line label that shortens itself with "…" instead of forcing its
    full text width onto the layout (long file names have no break points)."""

    def __init__(self, text: str = "", name: str = "") -> None:
        super().__init__()
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._full = ""
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full = text
        self._elide()

    def fullText(self) -> str:  # noqa: N802 - Qt API style
        return self._full

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(0, self.width()))
        super().setText(shown)


class Card(QFrame):
    """Group of rows drawn as separate tiles that read as one rounded block.

    There are no divider lines: a small gap of window background between the
    tiles separates the rows, and only the block's outer corners are fully
    rounded (see ``#Tile[pos=...]`` in the style sheet).
    """

    GAP = 2

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.GAP)
        self._tiles: List[QFrame] = []

    def add(self, widget: QWidget, margins=(14, 8, 12, 8)) -> QWidget:
        tile = QFrame()
        tile.setObjectName("Tile")
        lay = QVBoxLayout(tile)
        lay.setContentsMargins(*margins)
        lay.addWidget(widget)
        self._layout.addWidget(tile)
        self._tiles.append(tile)
        self._update_corners()
        return widget

    def _update_corners(self) -> None:
        last = len(self._tiles) - 1
        for i, tile in enumerate(self._tiles):
            pos = "only" if last == 0 else "first" if i == 0 else "last" if i == last else "middle"
            if tile.property("pos") != pos:
                tile.setProperty("pos", pos)
                tile.style().unpolish(tile)
                tile.style().polish(tile)

    def row(self, title: str, desc: Optional[str], *controls: QWidget) -> QWidget:
        """Title/description on the left, controls aligned right."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(title, "RowTitle", wrap=True))
        if desc:
            text.addWidget(label(desc, "RowDesc", wrap=True))
        h.addLayout(text, 1)
        h.addSpacing(4)
        for control in controls:
            h.addWidget(control, 0, Qt.AlignVCenter)
        return self.add(row)


def section(title: str, desc: Optional[str] = None) -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(4, 8, 0, 2)
    v.setSpacing(1)
    v.addWidget(label(upper(title), "SectionTitle"))
    if desc:
        v.addWidget(label(desc, "SectionDesc", wrap=True))
    return box


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class IconTextButton(QPushButton):
    """Push button that centres icon and text on the same optical midline.

    Qt's own layout aligns the icon to the text baseline, which leaves small
    glyph icons sitting visibly too high; here the background still comes from
    the style sheet but the content is painted manually.
    """

    GAP = 7

    def paintEvent(self, _event) -> None:
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        text, icon = self.text().strip(), self.icon()
        opt.text, opt.icon = "", QIcon()
        painter = QStylePainter(self)
        painter.drawControl(QStyle.CE_PushButton, opt)

        rect = self.contentsRect()
        fm = self.fontMetrics()
        icon_size = self.iconSize() if not icon.isNull() else QSize(0, 0)
        gap = self.GAP if text and icon_size.width() else 0
        available = max(0, rect.width() - icon_size.width() - gap - 8)
        shown = fm.elidedText(text, Qt.ElideRight, available)
        total = icon_size.width() + gap + fm.horizontalAdvance(shown)
        x = rect.left() + (rect.width() - total) / 2
        cy = rect.top() + rect.height() / 2
        if icon_size.width():
            mode = QIcon.Normal if self.isEnabled() else QIcon.Disabled
            pixmap = icon.pixmap(icon_size, self.devicePixelRatioF(), mode)
            painter.drawPixmap(QPointF(x, cy - icon_size.height() / 2), pixmap)
            x += icon_size.width() + gap
        painter.setPen(self.palette().color(QPalette.ButtonText) if self.isEnabled() else QColor(theme.DIM))
        # Centre the capitals, not the font's line box: Segoe UI has extra room
        # above the caps, so AlignVCenter leaves text visibly low.
        painter.drawText(QPointF(x, round(cy + fm.capHeight() / 2)), shown)


class NavButton(QPushButton):
    """Sidebar item: icon and label at fixed x positions, so the icons form one
    column (also with the menu button) and the labels another (with the brand)."""

    ICON_X = 11
    TEXT_X = 41

    def __init__(self, icon: QIcon, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavButton")
        self.setIcon(icon)
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _event) -> None:
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text, opt.icon = "", QIcon()
        painter = QStylePainter(self)
        painter.drawControl(QStyle.CE_PushButton, opt)
        size = self.iconSize()
        cy = self.height() / 2
        state = QIcon.On if self.isChecked() else QIcon.Off
        pixmap = self.icon().pixmap(size, self.devicePixelRatioF(), QIcon.Normal, state)
        painter.drawPixmap(QPointF(self.ICON_X, cy - size.height() / 2), pixmap)
        if self.text():
            fm = self.fontMetrics()
            shown = fm.elidedText(self.text(), Qt.ElideRight, max(0, self.width() - self.TEXT_X - 8))
            active = self.isChecked() or self.underMouse()
            painter.setPen(QColor(theme.TEXT if active else theme.MUTED))
            painter.drawText(QPointF(self.TEXT_X, round(cy + fm.capHeight() / 2)), shown)


class PrimaryButton(IconTextButton):
    def __init__(self, variant: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Primary")
        self.setMinimumHeight(36)
        self.setIconSize(QSize(15, 15))
        self.setCursor(Qt.PointingHandCursor)
        # Ignored: buttons share the row equally and may shrink instead of widening the page.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._variant = ""
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        if variant != self._variant:
            self._variant = variant
            self.setProperty("variant", variant)
            self.style().unpolish(self)
            self.style().polish(self)


def secondary_button(text: str, icon: Optional[str] = None, on_click: Optional[Callable] = None) -> QPushButton:
    btn = IconTextButton(text)
    btn.setObjectName("Secondary")
    btn.setMinimumHeight(28)
    btn.setCursor(Qt.PointingHandCursor)
    if icon:
        btn.setIcon(glyph_icon(icon, theme.TEXT, 14))
        btn.setIconSize(QSize(14, 14))
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def combo(values: Sequence[str], current: int, on_change: Callable[[int], None], width: int = 150) -> QComboBox:
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
    width: int = 100,
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


class DecimalSpin(QDoubleSpinBox):
    """Decimal input that accepts ``1.5`` or ``1,5`` and nothing else.

    The suffix (``×``, `` s``) may appear once, at the end; anything else such
    as ``1×3×`` or letters is rejected while typing. Values are shown without
    trailing zeros (``1.5×`` instead of the locale's ``1,50×``).
    """

    _NUMBER = re.compile(r"^(\d*)(?:[.,](\d*))?$")

    def textFromValue(self, value: float) -> str:
        return f"{value:g}"

    def _body(self, text: str) -> Optional[str]:
        """The number part of ``text``, or ``None`` if the text is malformed."""
        body = text.strip()
        prefix, suffix = self.prefix().strip(), self.suffix().strip()
        if prefix and body.startswith(prefix):
            body = body[len(prefix) :].strip()
        if suffix and body.endswith(suffix):
            body = body[: -len(suffix)].strip()
        match = self._NUMBER.match(body)
        if not match or len(match.group(2) or "") > self.decimals():
            return None
        return body

    def valueFromText(self, text: str) -> float:
        if self.specialValueText() and text.strip() == self.specialValueText():
            return self.minimum()
        body = self._body(text)
        try:
            return float(body.replace(",", ".")) if body else self.value()
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):
        if self.specialValueText() and text.strip() == self.specialValueText():
            return QValidator.Acceptable, text, pos
        body = self._body(text)
        if body is None:
            return QValidator.Invalid, text, pos
        if body in ("", ".", ","):
            return QValidator.Intermediate, text, pos
        value = float(body.replace(",", "."))
        if value > self.maximum():
            return QValidator.Invalid, text, pos
        if value < self.minimum():
            return QValidator.Intermediate, text, pos
        return QValidator.Acceptable, text, pos

    def fixup(self, text: str) -> str:
        return self.textFromValue(self.value()) + self.suffix()


def double_spin(
    value: float,
    lo: float,
    hi: float,
    on_change: Callable[[float], None],
    width: int = 100,
    suffix: str = "×",
    step: float = 0.25,
    special: str = "",
):
    box = DecimalSpin()
    box.setRange(lo, hi)
    box.setDecimals(2)
    box.setSingleStep(step)
    box.setValue(value)
    box.setSuffix(suffix)
    if special:
        box.setSpecialValueText(special)
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
        h.setSpacing(3)
        self._group = QButtonGroup(self)
        for i, text in enumerate(labels):
            btn = QPushButton(text)
            btn.setObjectName("SegmentButton")
            btn.setCheckable(True)
            btn.setMinimumHeight(24)
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
        self.setFixedSize(36, 20)
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
        return QSize(36, 20)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        off, on = QColor(theme.HOVER_HI), QColor(theme.BLUE)
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
        self.setFixedHeight(24)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 0, 12, 2)  # 2 px lift: optical centring of the text
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
            # A soft wash of the mode colour instead of an outline.
            self.setStyleSheet(f"#Pill {{ background: {theme.tint(color, 0.14)}; }}")
        if text != self._text.text():
            self._text.setText(text)
            # Size immediately, so a longer status is never drawn cut off for a frame.
            m = self.layout().contentsMargins()
            width = m.left() + self._dot.width() + self.layout().spacing() + m.right()
            self.setFixedWidth(width + self._text.fontMetrics().horizontalAdvance(text) + 2)
