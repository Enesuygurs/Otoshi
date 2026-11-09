import ctypes
import os
import threading

import pytest

from otoshi.hotkeys import (
    WM_HOTKEY,
    HotkeyManager,
    format_hotkey,
    hotkey_from_vk,
    normalize_hotkey,
    parse_hotkey,
    trigger_for,
    validate_hotkey,
)


@pytest.mark.parametrize("hotkey", ["f2", "ctrl+f2", "ctrl+shift+a", "page up", "alt+space", "ctrl+f12", "f24"])
def test_valid_hotkeys(hotkey):
    assert validate_hotkey(hotkey) is None


@pytest.mark.parametrize(
    "hotkey", ["", "a", "space", "num 5", "ctrl", "ctrl+shift", "prior", "control_l", "f12", "ctrl+a+b", "f25"]
)
def test_invalid_hotkeys(hotkey):
    assert validate_hotkey(hotkey) is not None


def test_parse_normalize_and_format():
    assert parse_hotkey("Shift+Ctrl+F2") == ({"ctrl", "shift"}, "f2")
    assert normalize_hotkey("Shift+Ctrl+F2") == "ctrl+shift+f2"
    assert normalize_hotkey("alt+escape") == "alt+esc"
    assert format_hotkey("ctrl+page up") == "Ctrl+Page Up"
    assert format_hotkey("windows+alt+a") == "Win+Alt+A"


def test_hotkey_from_vk():
    assert hotkey_from_vk({"shift", "ctrl"}, 0x74) == "ctrl+shift+f5"
    assert hotkey_from_vk(set(), 0x41) == "a"
    assert hotkey_from_vk(set(), 0xFF) is None


def test_trigger_for():
    trigger = trigger_for("ctrl+shift+f2")
    assert trigger.modifiers == {"ctrl", "shift"}
    assert trigger.names == {"f2"}
    assert trigger.vks == {0x71}
    assert trigger_for("ctrl") is None


@pytest.mark.skipif(os.name != "nt", reason="RegisterHotKey is Windows-only")
def test_manager_registers_and_dispatches():
    """Registers an unusual combination and posts WM_HOTKEY directly (no key is pressed)."""
    manager = HotkeyManager()
    fired = threading.Event()
    try:
        errors = manager.bind({"x": ("ctrl+alt+shift+f23", fired.set)})
        assert errors == {}
        hotkey_id = next(iter(manager._callbacks))
        ctypes.windll.user32.PostThreadMessageW(manager._thread_id, WM_HOTKEY, hotkey_id, 0)
        assert fired.wait(2.0)
        manager.unbind_all()
        assert manager._callbacks == {}
    finally:
        manager.shutdown()
