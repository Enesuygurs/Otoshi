"""Auto clicker engine: repeated mouse clicks or holding a key down."""

from __future__ import annotations

import random
import threading
import time
from typing import Callable, Optional, Sequence, Tuple

from pynput import keyboard as kb
from pynput import mouse as ms

from .logger import logger
from .timing import sleep_until

# Windows' own typematic behaviour: first repeat after ~0.5 s, then ~30 per second.
HOLD_REPEAT_DELAY = 0.5
HOLD_REPEAT_INTERVAL = 0.033


class AutoClicker:
    """Runs one job at a time on a worker thread.

    ``on_finish`` runs on the worker thread whenever a job ends, whether it was
    stopped or reached its click count / hold duration.
    """

    def __init__(self) -> None:
        self._mouse = ms.Controller()
        self._keyboard = kb.Controller()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.clicks_done = 0

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop.is_set()

    def _launch(self, target: Callable, args: tuple) -> bool:
        if self.is_running:
            return False
        self._join_previous()
        self._stop = threading.Event()
        self.clicks_done = 0
        self._thread = threading.Thread(target=target, args=(*args, self._stop), name="otoshi-clicker", daemon=True)
        self._thread.start()
        return True

    def start(
        self,
        interval_ms: int,
        button: str = "left",
        click_type: str = "single",
        count: int = 0,
        position: Optional[Tuple[int, int]] = None,
        on_finish: Optional[Callable[[], None]] = None,
        interval_max_ms: int = 0,
        rng: Optional[random.Random] = None,
    ) -> bool:
        """Click every ``interval_ms`` (or a random time up to ``interval_max_ms``)."""
        low = max(1, int(interval_ms))
        high = max(low, int(interval_max_ms or 0))
        return self._launch(
            self._click_worker,
            (
                low / 1000.0,
                high / 1000.0,
                getattr(ms.Button, button, ms.Button.left),
                2 if click_type == "double" else 1,
                max(0, int(count)),
                position,
                rng or random.Random(),
                on_finish,
            ),
        )

    def start_hold(
        self, vks: Sequence[int], duration_s: float = 0.0, on_finish: Optional[Callable[[], None]] = None
    ) -> bool:
        """Hold the given virtual keys down (0 = until stopped), repeating like a real held key."""
        if not vks:
            return False
        return self._launch(self._hold_worker, (list(vks), max(0.0, float(duration_s)), on_finish))

    def stop(self) -> None:
        self._stop.set()

    def _join_previous(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            self._stop.set()
            thread.join(timeout=1.0)

    def _click_worker(
        self,
        low: float,
        high: float,
        button: ms.Button,
        clicks_per_event: int,
        count: int,
        position: Optional[Tuple[int, int]],
        rng: random.Random,
        on_finish: Optional[Callable[[], None]],
        stop: threading.Event,
    ) -> None:
        next_at = time.perf_counter()
        warned = False
        try:
            while not stop.is_set():
                try:
                    if position is not None:
                        self._mouse.position = position
                    self._mouse.click(button, clicks_per_event)
                except Exception:
                    if not warned:
                        logger.exception("Auto clicker failed to click")
                        warned = True
                self.clicks_done += 1
                if count and self.clicks_done >= count:
                    break
                interval = rng.uniform(low, high) if high > low else low
                next_at += interval
                now = time.perf_counter()
                if next_at < now - interval:  # fell behind: do not burst to catch up
                    next_at = now
                if sleep_until(next_at, stop):
                    break
        finally:
            if on_finish is not None:
                on_finish()

    def _hold_worker(
        self, vks: Sequence[int], duration: float, on_finish: Optional[Callable[[], None]], stop: threading.Event
    ) -> None:
        keys = [kb.KeyCode.from_vk(vk) for vk in vks]
        pressed = []
        start = time.perf_counter()
        try:
            for key in keys:
                self._keyboard.press(key)
                pressed.append(key)
            self.clicks_done = 1
            next_repeat = start + HOLD_REPEAT_DELAY
            while True:
                deadline = next_repeat if not duration else min(next_repeat, start + duration)
                if sleep_until(deadline, stop):
                    break
                if duration and time.perf_counter() >= start + duration:
                    break
                self._keyboard.press(keys[-1])  # auto-repeat of the main key
                next_repeat += HOLD_REPEAT_INTERVAL
        except Exception:
            logger.exception("Key hold failed")
        finally:
            for key in reversed(pressed):
                try:
                    self._keyboard.release(key)
                except Exception:
                    pass
            if on_finish is not None:
                on_finish()

    def shutdown(self) -> None:
        self.stop()
        self._join_previous()
