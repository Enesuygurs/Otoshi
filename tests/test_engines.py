"""Engine behaviour with fake input controllers (nothing touches the real mouse)."""

import threading
import time

from pynput.keyboard import Key, KeyCode

from otoshi.clicker import AutoClicker
from otoshi.hotkeys import trigger_for
from otoshi.macro import MacroEngine


class FakeMouse:
    def __init__(self):
        self.log = []
        self.position = (0, 0)

    def click(self, button, count):
        self.log.append(("click", button.name, count, self.position))

    def press(self, button):
        self.log.append(("press", button.name))

    def release(self, button):
        self.log.append(("release", button.name))

    def scroll(self, dx, dy):
        self.log.append(("scroll", dx, dy))


class FakeKeyboard:
    def __init__(self):
        self.log = []

    def press(self, key):
        self.log.append(("press", key))

    def release(self, key):
        self.log.append(("release", key))


def wait_for(event, timeout=5.0):
    assert event.wait(timeout), "worker did not finish in time"


# -- auto clicker -------------------------------------------------------------


def test_clicker_stops_after_count_and_reports_once():
    clicker = AutoClicker()
    clicker._mouse = FakeMouse()
    done = threading.Event()
    calls = []
    clicker.start(1, "right", "double", count=5, position=(7, 8), on_finish=lambda: (calls.append(1), done.set()))
    wait_for(done)
    time.sleep(0.05)
    assert clicker.clicks_done == 5
    assert not clicker.is_running
    assert calls == [1]
    assert clicker._mouse.log == [("click", "right", 2, (7, 8))] * 5


def test_clicker_stop_is_immediate_even_with_long_interval():
    clicker = AutoClicker()
    clicker._mouse = FakeMouse()
    done = threading.Event()
    clicker.start(60_000, on_finish=done.set)
    time.sleep(0.05)
    clicker.stop()
    wait_for(done, timeout=1.0)
    assert clicker.clicks_done == 1


def test_clicker_restart_never_runs_two_threads():
    clicker = AutoClicker()
    clicker._mouse = FakeMouse()
    clicker.start(5)
    first = clicker._thread
    clicker.stop()
    clicker.start(5)
    assert not first.is_alive()
    clicker.shutdown()


# -- macro playback -----------------------------------------------------------


def make_engine(events):
    engine = MacroEngine()
    engine._mouse, engine._keyboard = FakeMouse(), FakeKeyboard()
    engine.events = events
    return engine


def test_playback_runs_requested_loops_with_speed():
    engine = make_engine(
        [
            {"t": 0.0, "type": "move", "x": 1, "y": 2},
            {"t": 0.2, "type": "click", "x": 1, "y": 2, "button": "left", "pressed": True},
            {"t": 0.2, "type": "click", "x": 1, "y": 2, "button": "left", "pressed": False},
        ]
    )
    done = threading.Event()
    start = time.perf_counter()
    assert engine.play(loops=3, speed=10.0, on_finish=done.set)
    wait_for(done)
    elapsed = time.perf_counter() - start
    assert engine._mouse.log.count(("press", "left")) == 3
    assert 0.05 <= elapsed < 1.0  # 3 loops x 0.02 s at 10x


def test_stopping_playback_releases_held_inputs():
    engine = make_engine(
        [
            {"t": 0.0, "type": "key", "key": {"name": "shift"}, "pressed": True},
            {"t": 0.0, "type": "click", "x": 0, "y": 0, "button": "left", "pressed": True},
            {"t": 30.0, "type": "key", "key": {"name": "shift"}, "pressed": False},
        ]
    )
    done = threading.Event()
    engine.play(loops=1, speed=1.0, on_finish=done.set)
    time.sleep(0.1)
    engine.stop_playback()
    wait_for(done, timeout=1.0)
    assert ("release", Key.shift) in engine._keyboard.log
    assert ("release", "left") in engine._mouse.log


def test_play_refuses_empty_macro():
    assert not make_engine([]).play(1, 1.0)


# -- hotkey filtering while recording ---------------------------------------


def test_recording_swallows_hotkeys_but_keeps_other_keys():
    engine = MacroEngine()
    engine._triggers = [trigger_for("f2"), trigger_for("ctrl+f3")]
    f2, f3, a = Key.f2, Key.f3, KeyCode(vk=65, char="a")

    engine._on_key(a, True)
    engine._on_key(a, False)
    engine._on_key(f2, True)  # plain F2 -> hotkey
    engine._on_key(f2, False)
    engine._on_key(f3, True)  # F3 without Ctrl -> regular key
    engine._on_key(f3, False)
    engine._on_key(Key.ctrl_l, True)
    engine._on_key(f3, True)  # Ctrl+F3 -> hotkey
    engine._on_key(Key.ctrl_l, False)
    engine._on_key(f3, False)  # release after the modifier is still swallowed

    keys = [(e["key"], e["pressed"]) for e in engine._buffer]
    assert keys == [
        ({"vk": 65, "char": "a"}, True),
        ({"vk": 65, "char": "a"}, False),
        ({"name": "f3"}, True),
        ({"name": "f3"}, False),
        ({"name": "ctrl_l"}, True),
        ({"name": "ctrl_l"}, False),
    ]
