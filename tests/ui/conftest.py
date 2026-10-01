"""UI-only pytest fixtures and defensive desktop runtime stubs."""

from __future__ import annotations

import pytest

from ui._support import *  # noqa: F401,F403


@pytest.fixture(autouse=True)
def isolated_startup_directory(tmp_path, monkeypatch):
    """Do not read or change the real user's Windows startup state in UI tests."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
