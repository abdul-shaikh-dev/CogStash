"""Windows startup commands for the opt-in Qt candidate."""
from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cogstash.ui.install_state import get_startup_shortcut_path


def startup_command(config_path: Path) -> list[str]:
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return [str(executable), "--config", str(config_path.resolve())]
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.is_file():
        executable = pythonw
    return [str(executable), "-m", "cogstash.ui.qt.candidate", "--config", str(config_path.resolve())]


def batch_contents(command: list[str]) -> bytes:
    """Quote literal batch arguments, including percent and delayed expansion."""
    if not command or any(not value or any(c in value for c in '\r\n\x00"') for value in command):
        raise ValueError("Startup command contains an invalid argument.")
    quoted = [f'"{value.replace("%", "%%")}"' for value in command]
    return ('@echo off\r\nsetlocal DisableDelayedExpansion\r\nchcp 65001 >nul\r\nstart "" ' + " ".join(quoted) + '\r\n').encode("utf-8")


class StartupManager:
    path: Path
    contents: bytes

    def __init__(self, config_path: Path) -> None:
        if sys.platform != "win32" or not os.environ.get("APPDATA"):
            raise OSError("Windows startup requires a valid APPDATA directory.")
        self.path = get_startup_shortcut_path()
        self.contents = batch_contents(startup_command(config_path))

    def snapshot(self) -> bytes | None:
        return self.path.read_bytes() if self.path.exists() else None

    def write(self, contents: bytes | None) -> None:
        if contents is None:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="CogStash-", suffix=".tmp", dir=self.path.parent)
        os.close(fd)
        staged = Path(name)
        try:
            staged.write_bytes(contents)
            staged.replace(self.path)
        finally:
            staged.unlink(missing_ok=True)

    @contextmanager
    def change(self, enabled: bool, baseline: bytes | None) -> Iterator[None]:
        if self.snapshot() != baseline:
            raise ValueError("Startup changed elsewhere. Reopen Settings before saving.")
        # Preserve installer-created commands unless the user toggles startup.
        if enabled == (baseline is not None):
            yield
            return
        desired = self.contents if enabled else None
        self.write(desired)
        try:
            yield
        except Exception as exc:
            try:
                if self.snapshot() != desired:
                    raise OSError("Startup changed again; automatic rollback would overwrite it.")
                self.write(baseline)
            except OSError as rollback:
                raise OSError(f"Settings were not saved. Startup rollback failed: {rollback}. Review Windows startup manually.") from exc
            raise
