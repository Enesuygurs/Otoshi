"""Precise, interruptible waiting used by the playback and clicker threads."""

from __future__ import annotations

import threading
import time

# Event.wait() is only ~15 ms accurate on Windows, time.sleep() is much finer
# (high-resolution timer since Python 3.11). Coarse-wait first, then fine-sleep.
_COARSE_MARGIN = 0.03


def sleep_until(deadline: float, stop: threading.Event) -> bool:
    """Block until ``time.perf_counter() >= deadline``.

    Returns ``True`` if ``stop`` was set before the deadline was reached.
    """
    while True:
        if stop.is_set():
            return True
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return False
        if remaining > _COARSE_MARGIN * 2:
            stop.wait(remaining - _COARSE_MARGIN)
        else:
            time.sleep(remaining)
