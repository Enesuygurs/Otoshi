"""Auto clicker engine."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Tuple

from pynput import mouse as ms

from .logger import logger
from .timing import sleep_until


class AutoClicker:
    """Clicks on a worker thread at a fixed interval until stopped or a count is reached.

    ``on_finish`` runs on the worker thread whenever the loop ends, whether it
    was stopped or reached its click count.
    """

    def __init__(self) -> None:
        self._mouse = ms.Controller()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.clicks_done = 0

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop.is_set()

    def start(
        self,
        interval_ms: int,
        button: str = "left",
        click_type: str = "single",
        count: int = 0,
        position: Optional[Tuple[int, int]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> bool:
        if self.is_running:
            return False
        self._join_previous()
        self._stop = threading.Event()
        self.clicks_done = 0
        self._thread = threading.Thread(
            target=self._worker,
            args=(
                max(1, int(interval_ms)) / 1000.0,
                getattr(ms.Button, button, ms.Button.left),
                2 if click_type == "double" else 1,
                max(0, int(count)),
                position,
                self._stop,
                on_finish,
            ),
            name="otoshi-clicker",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _join_previous(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            self._stop.set()
            thread.join(timeout=1.0)

    def _worker(
        self,
        interval: float,
        button: ms.Button,
        clicks_per_event: int,
        count: int,
        position: Optional[Tuple[int, int]],
        stop: threading.Event,
        on_finish: Optional[Callable[[], None]],
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
                next_at += interval
                now = time.perf_counter()
                if next_at < now - interval:  # fell behind: do not burst to catch up
                    next_at = now
                if sleep_until(next_at, stop):
                    break
        finally:
            if on_finish is not None:
                on_finish()

    def shutdown(self) -> None:
        self.stop()
        self._join_previous()
