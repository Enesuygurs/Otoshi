"""System tray icon (pystray). Menu callbacks run on the tray thread."""

from __future__ import annotations

import threading
from typing import Callable, List, Optional, Tuple

from PIL import Image

from .logger import logger

MenuSpec = List[Optional[Tuple[str, Callable[[], None], bool]]]  # None = separator


def _zero_arg(action: Callable[[], None]) -> Callable[[], None]:
    # pystray inspects ``__code__.co_argcount`` to decide how to call actions,
    # so hand it a plain function without parameters.
    def run() -> None:
        action()

    return run


class TrayIcon:
    def __init__(self, name: str, image: Image.Image, title: str, menu: MenuSpec) -> None:
        self._name, self._image, self._title, self._menu_spec = name, image, title, menu
        self._icon = None

    @property
    def available(self) -> bool:
        return self._icon is not None

    def _build_menu(self, pystray):
        items = []
        for entry in self._menu_spec:
            if entry is None:
                items.append(pystray.Menu.SEPARATOR)
            else:
                text, action, default = entry
                items.append(pystray.MenuItem(text, _zero_arg(action), default=default))
        return pystray.Menu(*items)

    def start(self) -> bool:
        try:
            import pystray

            self._icon = pystray.Icon(self._name, self._image, self._title, self._build_menu(pystray))
            threading.Thread(target=self._icon.run, name="otoshi-tray", daemon=True).start()
            return True
        except Exception:
            logger.exception("System tray is not available")
            self._icon = None
            return False

    def set_menu(self, menu: MenuSpec) -> None:
        """Replace the menu (e.g. after a language change)."""
        self._menu_spec = menu
        if self._icon is None:
            return
        try:
            import pystray

            self._icon.menu = self._build_menu(pystray)
            self._icon.update_menu()
        except Exception:
            logger.debug("Tray menu update failed", exc_info=True)

    def update(self, image: Image.Image, title: str) -> None:
        if self._icon is None:
            return
        try:
            self._icon.icon = image
            self._icon.title = title
        except Exception:
            logger.debug("Tray update failed", exc_info=True)

    def notify(self, message: str, title: str) -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title)
        except Exception:
            logger.debug("Tray notification failed", exc_info=True)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                logger.debug("Tray stop failed", exc_info=True)
            self._icon = None
