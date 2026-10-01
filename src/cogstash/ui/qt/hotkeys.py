"""Own the system-wide listener without allowing it to touch widgets."""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

logger = logging.getLogger(__name__)


class HotkeyAdapter(QObject):
    activated = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.listener: Any = None
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.check_health)

    def start(self, hotkey: str) -> None:
        if self.closed or self.listener is not None:
            return
        if sys.platform.startswith("linux") and (
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or os.environ.get("WAYLAND_DISPLAY")
        ):
            self.failed.emit("Global hotkeys are unavailable on Wayland with this backend. Use Capture or an X11 session.")
            return
        try:
            from pynput.keyboard import GlobalHotKeys

            self.listener = GlobalHotKeys({hotkey: self.activated.emit})
            self.listener.start()
            self.timer.start()
        except Exception as exc:
            self._release()
            self.failed.emit(self.failure_message(str(exc)))

    @Slot()
    def check_health(self) -> None:
        if self.closed or self.listener is None or self.listener.is_alive():
            return
        detail = "the listener stopped unexpectedly"
        try:
            self.listener.join(timeout=0)
        except Exception as exc:
            detail = str(exc)
        self._release()
        self.failed.emit(self.failure_message(detail))

    @staticmethod
    def failure_message(detail: str) -> str:
        guidance = "Check the shortcut and permissions, then restart."
        if sys.platform == "darwin":
            guidance = "Check Accessibility permission for CogStash or the Python launcher, then restart."
        return f"Global hotkey unavailable: {detail}. {guidance} Use Capture meanwhile."

    def _release(self) -> None:
        self.timer.stop()
        listener, self.listener = self.listener, None
        if listener is None:
            return
        # stop() can race the thread's initialization. Retry once after a bounded join.
        for _attempt in range(2):
            try:
                listener.stop()
            except Exception:
                logger.exception("Could not stop the hotkey listener")
            try:
                listener.join(timeout=0.5 if listener.is_alive() else 0)
            except Exception:
                logger.exception("Hotkey listener ended with an error")
            if not listener.is_alive():
                break
        if listener.is_alive():
            # Retain ownership so a later start cannot create a second listener.
            self.listener = listener
            logger.warning("Hotkey listener did not stop within one second")

    @Slot()
    def shutdown(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._release()
