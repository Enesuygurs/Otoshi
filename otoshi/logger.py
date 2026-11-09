"""Logging setup: a size-rotated file in the data directory plus console output."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .paths import log_dir

logger = logging.getLogger("otoshi")

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure handlers once. Safe to call more than once."""
    if logger.handlers:
        return
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(_FORMAT)

    try:
        file_handler = RotatingFileHandler(
            log_dir() / "otoshi.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:  # read-only profile, permissions, ...
        print(f"Otoshi: file logging disabled ({exc})", file=sys.stderr or sys.__stdout__)

    # Windowed (PyInstaller --noconsole) builds have no stderr.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(formatter)
        logger.addHandler(console)

    _install_exception_hooks()


def _install_exception_hooks() -> None:
    def excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        logger.error(
            "Unhandled exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
