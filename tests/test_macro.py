import json
import os
import pickle

import pytest
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button

from otoshi.macro import (
    FILE_FORMAT,
    MacroFileError,
    key_to_spec,
    load_macro,
    sanitize_events,
    save_macro,
    spec_to_key,
)


def click(t, pressed, x=10, y=10, button="left"):
    return {"t": t, "type": "click", "x": x, "y": y, "button": button, "pressed": pressed}


def key(t, pressed, vk=65):
    return {"t": t, "type": "key", "key": {"vk": vk, "char": "a"}, "pressed": pressed}


def move(t, x=1, y=1):
    return {"t": t, "type": "move", "x": x, "y": y}


# -- key specs -------------------------------------------------------------


def test_key_spec_roundtrip():
    assert spec_to_key(key_to_spec(Key.shift)) == Key.shift
    code = spec_to_key(key_to_spec(KeyCode(vk=65, char="a")))
    assert code.vk == 65 and code.char == "a"
    assert spec_to_key({"name": "no_such_key"}) is None
    assert spec_to_key({}) is None


# -- sanitising --------------------------------------------------------------


def test_drops_release_without_press_and_press_without_release():
    events = [click(0.1, False), key(0.2, True), key(0.3, False), key(0.4, True, vk=17)]
    assert sanitize_events(events) == [key(0.2, True), key(0.3, False)]


def test_keeps_auto_repeat_presses():
    events = [key(0.1, True), key(0.2, True), key(0.3, True), key(0.4, False)]
    assert sanitize_events(events) == events


def test_trims_trailing_clicks_on_own_window():
    rect = (100, 100, 200, 200)
    events = [
        move(0.1),
        click(0.2, True),
        click(0.3, False),
        move(0.4, 150, 150),
        click(0.5, True, 150, 150),
        click(0.6, False, 150, 150),
        move(0.7),
    ]
    assert sanitize_events(events, rect) == events[:4]


def test_keeps_clicks_on_own_window_that_are_not_trailing():
    rect = (100, 100, 200, 200)
    events = [click(0.1, True, 150, 150), click(0.2, False, 150, 150), key(0.3, True), key(0.4, False)]
    assert sanitize_events(events, rect) == events


# -- files -------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    events = [
        move(0.0),
        click(0.1, True),
        click(0.2, False),
        key(0.3, True),
        key(0.4, False),
        {"t": 0.5, "type": "scroll", "x": 1, "y": 2, "dx": 0, "dy": -1},
    ]
    path = tmp_path / "m.otm"
    save_macro(path, events, loop_count=3, speed=2.5)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == FILE_FORMAT
    loaded = load_macro(path)
    assert loaded.events == events
    assert loaded.loop_count == 3 and loaded.speed == 2.5 and not loaded.legacy


def test_load_skips_malformed_events_and_sorts(tmp_path):
    path = tmp_path / "m.otm"
    payload = {
        "format": FILE_FORMAT,
        "version": 2,
        "events": [
            move(0.5),
            {"t": "x", "type": "move"},
            {"t": -1, "type": "move", "x": 1, "y": 1},
            {"t": 0.1, "type": "teleport"},
            move(0.2),
            "junk",
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert [e["t"] for e in load_macro(path).events] == [0.2, 0.5]


@pytest.mark.parametrize("content", [b"hello", b'{"format": "something-else"}', b"[]"])
def test_rejects_foreign_files(tmp_path, content):
    path = tmp_path / "x.otm"
    path.write_bytes(content)
    with pytest.raises(MacroFileError):
        load_macro(path)


def test_rejects_newer_versions(tmp_path):
    path = tmp_path / "x.otm"
    path.write_text(json.dumps({"format": FILE_FORMAT, "version": 99, "events": [move(0)]}))
    with pytest.raises(MacroFileError, match="newer"):
        load_macro(path)


def test_imports_legacy_pickle_files(tmp_path):
    legacy = {
        "events": [
            {"time": 0.1, "type": "move", "pos": (5, 6)},
            {"time": 0.2, "type": "click", "pos": (5, 6), "button": Button.left, "pressed": True},
            {"time": 0.3, "type": "click", "pos": (5, 6), "button": Button.left, "pressed": False},
            {"time": 0.4, "type": "keypress", "key": KeyCode(vk=65, char="a")},
            {"time": 0.5, "type": "keyrelease", "key": KeyCode(vk=65, char="a")},
            {"time": 0.6, "type": "keypress", "key": Key.shift},
            {"time": 0.7, "type": "keyrelease", "key": Key.shift},
            {"time": 0.8, "type": "scroll", "pos": (5, 6), "dx": 0, "dy": 1},
        ],
        "loop_count": 4,
    }
    path = tmp_path / "old.otm"
    path.write_bytes(pickle.dumps(legacy))
    loaded = load_macro(path)
    assert loaded.legacy and loaded.loop_count == 4
    assert loaded.events[1] == click(0.2, True, 5, 6)
    assert loaded.events[3] == {"t": 0.4, "type": "key", "key": {"vk": 65, "char": "a"}, "pressed": True}
    assert loaded.events[5]["key"] == {"name": "shift"}


class _Exploit:
    def __reduce__(self):
        return (os.system, ("echo pwned",))


def test_legacy_loader_refuses_code_execution(tmp_path):
    path = tmp_path / "evil.otm"
    path.write_bytes(pickle.dumps({"events": [_Exploit()]}))
    with pytest.raises(MacroFileError):
        load_macro(path)
