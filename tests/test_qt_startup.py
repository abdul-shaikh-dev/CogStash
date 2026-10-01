from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from cogstash.core import CogStashConfig
from cogstash.core.config import save_config
from cogstash.ui.qt import settings, startup


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    return startup.StartupManager(tmp_path / "config.json")


def test_batch_arguments_are_literal_and_unicode_safe():
    contents = startup.batch_contents([r"C:\Program Files\CogStash.exe", "--config", r"C:\notes & stuff\100% !世界.json"]).decode("utf-8")
    assert '"C:\\Program Files\\CogStash.exe"' in contents
    assert '"C:\\notes & stuff\\100%% !世界.json"' in contents
    assert "DisableDelayedExpansion" in contents
    assert "chcp 65001 >nul" in contents


@pytest.mark.parametrize("argument", ['bad"arg', 'bad\narg', 'bad\x00arg', ''])
def test_batch_rejects_invalid_arguments(argument):
    with pytest.raises(ValueError):
        startup.batch_contents([argument])


def test_startup_source_and_frozen_commands(tmp_path, monkeypatch):
    executable = tmp_path / "python.exe"
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    path = tmp_path / "config.json"
    command = startup.startup_command(path)
    assert command == [str(executable), "-m", "cogstash.ui.qt.candidate", "--config", str(path)]
    monkeypatch.setattr(sys, "frozen", True)
    assert startup.startup_command(path) == [str(executable), "--config", str(path)]


def test_startup_change_preserves_existing_installer_command(manager):
    baseline = b'@echo off\nstart "" "installed.exe"\n'
    manager.write(baseline)
    with manager.change(True, baseline):
        assert manager.snapshot() == baseline
    with manager.change(False, baseline):
        assert manager.snapshot() is None
    with manager.change(True, None):
        assert manager.snapshot() == manager.contents


def test_startup_rolls_back_failed_config_save(manager):
    baseline = b"installer startup"
    manager.write(baseline)
    with pytest.raises(OSError, match="config failed"):
        with manager.change(False, baseline):
            raise OSError("config failed")
    assert manager.snapshot() == baseline
    manager.write(None)
    with pytest.raises(OSError):
        with manager.change(True, None):
            raise OSError("config failed")
    assert manager.snapshot() is None


def test_startup_detects_external_changes_and_preserves_them(manager):
    manager.write(b"external")
    with pytest.raises(ValueError, match="changed elsewhere"):
        with manager.change(True, None):
            pytest.fail("Unexpected transaction")
    assert manager.snapshot() == b"external"
    with pytest.raises(OSError, match="rollback failed"):
        with manager.change(False, b"external"):
            manager.write(b"second external edit")
            raise OSError("save failed")
    assert manager.snapshot() == b"second external edit"


def test_candidate_settings_cancel_and_save_startup(app, manager, tmp_path):
    config = CogStashConfig(output_file=tmp_path / "notes.md")
    path = tmp_path / "config.json"
    changes = []
    dialog = settings.SettingsDialog(config, path, changes.append, startup=manager)
    assert dialog.startup.isEnabled()
    dialog.startup.setChecked(True)
    assert dialog.has_changes()
    dialog.reject()
    assert manager.snapshot() is None and not path.exists()
    dialog = settings.SettingsDialog(config, path, changes.append, startup=manager)
    dialog.startup.setChecked(True)
    dialog.save()
    assert manager.snapshot() == manager.contents
    assert settings.read_config(path).launch_at_startup
    assert changes[0].launch_at_startup


def test_candidate_settings_failure_rolls_back_startup_and_keeps_draft(app, manager, tmp_path, monkeypatch):
    config = CogStashConfig(output_file=tmp_path / "notes.md")
    path = tmp_path / "config.json"
    save_config(config, path)
    baseline = path.read_bytes()
    dialog = settings.SettingsDialog(config, path, lambda c: pytest.fail("unexpected save"), startup=manager)
    dialog.startup.setChecked(True)
    monkeypatch.setattr(settings, "save_config", lambda *args: None)
    dialog.save()
    assert "Could not save" in dialog.error.text()
    assert dialog.startup.isChecked()
    assert manager.snapshot() is None and path.read_bytes() == baseline
    dialog.reject()


def test_startup_write_failure_does_not_persist_config(app, manager, tmp_path, monkeypatch):
    config = CogStashConfig(output_file=tmp_path / "notes.md")
    path = tmp_path / "config.json"
    dialog = settings.SettingsDialog(config, path, lambda c: pytest.fail("unexpected save"), startup=manager)
    dialog.startup.setChecked(True)
    def fail(contents):
        raise PermissionError("startup denied")
    monkeypatch.setattr(manager, "write", fail)
    dialog.save()
    assert "startup denied" in dialog.error.text()
    assert not path.exists()
    dialog.reject()


def test_candidate_default_config_is_only_used_for_installed_profile(tmp_path, monkeypatch):
    from cogstash.core import config as core_config
    from cogstash.ui.qt import app as application
    from cogstash.ui.qt.__main__ import main
    path = tmp_path / "default.json"
    calls = []
    monkeypatch.setattr(core_config, "get_default_config_path", lambda: path)
    monkeypatch.setattr(sys, "argv", ["candidate", "--no-hotkey"])
    monkeypatch.setattr(application, "run", lambda *args, **kwargs: calls.append((args, kwargs)) or 0)
    assert main(installed=True) == 0
    assert calls[0][0][-1] == path
    assert calls[0][1] == {"installed": True}
    assert not path.exists()
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


@pytest.mark.parametrize("already_running", [False, True])
def test_candidate_owns_single_instance_guard(tmp_path, monkeypatch, already_running):
    from types import SimpleNamespace

    from cogstash.ui import windows
    from cogstash.ui.qt import app as application
    from cogstash.ui.qt.__main__ import main
    closed = []
    guard = None if already_running else SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(windows, "acquire_single_instance", lambda: guard)
    monkeypatch.setattr(sys, "argv", ["candidate", "--config", str(tmp_path / "config.json"), "--no-hotkey"])
    def run(*args, **kwargs):
        raise RuntimeError("startup failed")
    monkeypatch.setattr(application, "run", run)
    if already_running:
        with pytest.raises(SystemExit) as exc:
            main(installed=True)
        assert exc.value.code == 0 and not closed
    else:
        with pytest.raises(RuntimeError, match="startup failed"):
            main(installed=True)
        assert closed == [True]
