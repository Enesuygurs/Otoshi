"""Input widgets: what can and cannot be typed (runs Qt off-screen)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QValidator  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from otoshi.widgets import double_spin, spin  # noqa: E402

ACCEPTABLE, INTERMEDIATE, INVALID = QValidator.Acceptable, QValidator.Intermediate, QValidator.Invalid


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def state(box, text):
    return box.validate(text, len(text))[0]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1.5×", ACCEPTABLE), ("2,5×", ACCEPTABLE), ("3", ACCEPTABLE), ("100×", ACCEPTABLE),
        ("1×3×", INVALID), ("1×3", INVALID), ("abc×", INVALID), ("1..2×", INVALID), ("1.234×", INVALID),
        ("1000×", INVALID), ("-1×", INVALID), ("×1", INVALID),
        ("", INTERMEDIATE), ("×", INTERMEDIATE), ("0×", INTERMEDIATE), ("0.", INTERMEDIATE),
    ],
)  # fmt: skip
def test_speed_box_validation(text, expected):
    box = double_spin(1.0, 0.1, 100.0, lambda v: None)
    assert state(box, text) == expected


def test_seconds_box_with_special_text():
    box = double_spin(0.0, 0.0, 3600.0, lambda v: None, suffix=" s", special="Off")
    assert box.text() == "Off"
    assert state(box, "Off") == ACCEPTABLE
    assert state(box, "1,5 s") == ACCEPTABLE
    assert state(box, "1 s2 s") == INVALID
    assert state(box, "Off5") == INVALID


def test_typing_cannot_build_garbage():
    box = double_spin(1.0, 0.1, 100.0, lambda v: None)
    box.selectAll()
    QTest.keyClicks(box, "1×3×")
    assert box.text().count("×") <= 1
    box.lineEdit().selectAll()
    QTest.keyClicks(box, "2,5")
    QTest.keyClick(box, Qt.Key_Enter)
    assert box.value() == 2.5
    assert box.text() == "2.5×"


@pytest.mark.parametrize("text", ["10 ms20 ms", "abc ms", "5000000 ms", "-5 ms"])
def test_integer_box_rejects_garbage(text):
    box = spin(1000, 1, 3_600_000, lambda v: None, suffix=" ms")
    assert state(box, text) == INVALID


def test_integer_box_special_and_prefix():
    loops = spin(0, 0, 1_000_000, lambda v: None, special="∞")
    assert loops.text() == "∞"
    assert state(loops, "5") == ACCEPTABLE
    coord = spin(0, -100_000, 100_000, lambda v: None)
    coord.setPrefix("X  ")
    assert state(coord, "X  -50") == ACCEPTABLE
    assert state(coord, "X  5X  5") == INVALID
