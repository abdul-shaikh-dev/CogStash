from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from cogstash import __version__
from cogstash.core import CogStashConfig
from cogstash.core.config import save_config
from cogstash.ui.qt import settings
from cogstash.ui.qt.app import apply_theme
from cogstash.ui.qt.runtime import Runtime


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config(tmp_path):
    return CogStashConfig(output_file=tmp_path / "notes.md", log_file=tmp_path / "keep.log",
                          last_seen_version=__version__, last_seen_installer_version="keep-version")


@pytest.fixture
def dialog(app, config, tmp_path):
    path = tmp_path / "settings.json"
    save_config(config, path)
    changes = []
    widget = settings.SettingsDialog(config, path, changes.append)
    widget.changes = changes
    yield widget
    widget.reject()


def test_cancel_changes_nothing(dialog, config):
    baseline = dialog.config_path.read_bytes()
    dialog.theme.setCurrentText("light")
    dialog.notes.setText("changed.md")
    dialog.add_tag("private", "X", "#abcdef")
    dialog.reject()
    assert dialog.config_path.read_bytes() == baseline
    assert not dialog.changes
    assert config.theme == "tokyo-night"
    assert config.tags is None


def test_save_preserves_unrelated_and_unknown_fields(app, config, tmp_path):
    path = tmp_path / "settings.json"
    save_config(config, path)
    data = json.loads(path.read_text())
    data["future_field"] = {"value": 42}
    path.write_text(json.dumps(data), encoding="utf-8")
    changes = []
    dialog = settings.SettingsDialog(config, path, changes.append)
    dialog.theme.setCurrentText("light")
    dialog.window_size.setCurrentText("wide")
    dialog.add_tag("research", "R", "#aabbcc")
    dialog.save()
    saved = settings.read_config(path)
    assert saved.theme == "light" and saved.window_size == "wide"
    assert saved.log_file == config.log_file
    assert saved.last_seen_installer_version == "keep-version"
    assert saved.tags == {"research": {"emoji": "R", "color": "#aabbcc"}}
    assert json.loads(path.read_text())["future_field"] == {"value": 42}
    assert changes == [saved]
    assert config.tags is None


@pytest.mark.parametrize("target", ["", "   ", "directory", "same-config", "file-parent", "null"])
def test_invalid_paths_leave_dialog_and_config(dialog, tmp_path, target):
    before = dialog.config_path.read_bytes()
    if target == "directory":
        target = str(tmp_path)
    elif target == "same-config":
        target = str(dialog.config_path)
    elif target == "file-parent":
        target = str(dialog.config_path / "notes.md")
    elif target == "null":
        target = "bad\x00.md"
    dialog.notes.setText(target)
    dialog.save()
    assert "Could not save" in dialog.error.text()
    assert not dialog.changes
    assert dialog.config_path.read_bytes() == before


@pytest.mark.parametrize("failure", ["serializer", "replace"])
def test_write_failure_retains_draft_and_original(dialog, monkeypatch, failure):
    baseline = dialog.config_path.read_bytes()
    dialog.theme.setCurrentText("dracula")
    if failure == "serializer":
        monkeypatch.setattr(settings, "save_config", lambda *args: None)
    else:
        def fail(*args):
            raise PermissionError("locked config")
        monkeypatch.setattr(settings.Path, "replace", fail)
    dialog.save()
    assert "Could not save" in dialog.error.text()
    assert dialog.theme.currentText() == "dracula"
    assert not dialog.changes
    assert dialog.config_path.read_bytes() == baseline
    assert not list(dialog.config_path.parent.glob("*.tmp"))


def test_external_change_is_not_overwritten(dialog):
    dialog.config_path.write_text('{"external": true}', encoding="utf-8")
    dialog.save()
    assert "changed elsewhere" in dialog.error.text()
    assert json.loads(dialog.config_path.read_text()) == {"external": True}
    assert not dialog.changes


@pytest.mark.parametrize("name,emoji,color", [("two words", "X", "#abcdef"), ("ok", "", "#abcdef"), ("ok", "X", "red")])
def test_invalid_tag_rows(dialog, name, emoji, color):
    dialog.add_tag(name, emoji, color)
    dialog.save()
    assert "Tag row" in dialog.error.text()
    assert not dialog.changes


def test_duplicate_and_remove_tags(dialog):
    dialog.add_tag("idea", "I", "#ffffff")
    dialog.add_tag("IDEA", "J", "#ffffff")
    dialog.save()
    assert "Duplicate" in dialog.error.text()
    dialog.tags.removeRow(1)
    dialog.save()
    assert dialog.changes[0].tags["idea"]["emoji"] == "I"


def test_removing_last_tag_removes_stored_tags(app, config, tmp_path):
    config.tags = {"test": {"emoji": "T", "color": "#ffffff"}}
    path = tmp_path / "settings.json"
    save_config(config, path)
    dialog = settings.SettingsDialog(config, path, lambda value: None)
    dialog.tags.removeRow(0)
    dialog.save()
    assert "tags" not in json.loads(path.read_text())


def test_hotkey_check_reports_syntax_without_registration(dialog, monkeypatch):
    parsed = []
    def parse(value):
        parsed.append(value)
        if value == "bad":
            raise ValueError("invalid")
    monkeypatch.setitem(sys.modules, "pynput.keyboard", SimpleNamespace(HotKey=SimpleNamespace(parse=parse)))
    dialog.hotkey.setText("bad")
    dialog.test_hotkey()
    assert "Enter a hotkey" in dialog.error.text()
    dialog.save()
    assert not dialog.changes
    dialog.hotkey.setText("<ctrl>+j")
    dialog.test_hotkey()
    assert "does not test OS permissions" in dialog.error.text()
    assert not dialog.changes
    dialog.save()
    assert dialog.changes[0].hotkey == "<ctrl>+j"
    assert parsed == ["bad", "bad", "<ctrl>+j", "<ctrl>+j"]


def test_empty_hotkey_is_invalid(dialog):
    dialog.hotkey.clear()
    dialog.save()
    assert "Hotkey is required" in dialog.error.text()


def test_read_config_missing_does_not_create(tmp_path):
    path = tmp_path / "missing.json"
    assert settings.read_config(path).last_seen_version == ""
    assert not path.exists()


@pytest.mark.parametrize("text", ['[]', '{', '{"theme": []}', '{"tags": []}', '{"tags": {"a": {"emoji": 2, "color": []}}}', '{"launch_at_startup": "false"}'])
def test_malformed_config_is_not_reset(tmp_path, text):
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        settings.read_config(path)
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("seen,installed_seen,installed,expected", [
    ("", "", False, "setup"), ("", "", True, "setup"),
    ("old", "old", True, "installed"), (__version__, "old", True, "installed"),
    ("old", "old", False, "updated"), (__version__, __version__, True, None),
    (__version__, "", False, None),
])
def test_onboarding_selection(config, monkeypatch, seen, installed_seen, installed, expected):
    monkeypatch.setattr(settings.install_state, "is_installed_windows_run", lambda: installed)
    config.last_seen_version = seen
    config.last_seen_installer_version = installed_seen
    assert settings.onboarding_kind(config) == expected


def test_setup_cancel_and_finish(app, config, tmp_path, monkeypatch):
    monkeypatch.setattr(settings.install_state, "is_installed_windows_run", lambda: True)
    path = tmp_path / "new.json"
    config.last_seen_version = ""
    changes = []
    dialog = settings.SettingsDialog(config, path, changes.append, setup=True)
    dialog.reject()
    assert not path.exists() and not changes
    dialog = settings.SettingsDialog(config, path, changes.append, setup=True)
    dialog.save()
    assert changes[0].last_seen_version == __version__
    assert changes[0].last_seen_installer_version == __version__
    assert config.last_seen_version == ""


def test_welcome_acknowledgement_is_persisted_only_on_success(app, config, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    save_config(config, path)
    changes = []
    dialog = settings.WelcomeDialog(config, path, "installed", changes.append)
    dialog.reject()
    assert not changes
    baseline = path.read_bytes()
    real_save = settings.save_config
    monkeypatch.setattr(settings, "save_config", lambda *args: None)
    dialog.findChild(QPushButton).click()
    assert "Could not save" in dialog.error.text()
    assert path.read_bytes() == baseline
    monkeypatch.setattr(settings, "save_config", real_save)
    dialog.findChild(QPushButton).click()
    assert changes[0].last_seen_installer_version == __version__


def test_startup_is_read_only_and_opening_does_not_persist(app, config, tmp_path, monkeypatch):
    monkeypatch.setattr(settings.install_state, "startup_script_exists", lambda: True)
    changes = []
    path = tmp_path / "missing.json"
    dialog = settings.SettingsDialog(config, path, changes.append)
    assert not dialog.startup.isEnabled()
    assert dialog.startup.isChecked() == (os.name == "nt")
    assert not path.exists() and not changes
    dialog.reject()


def test_runtime_apply_preserves_capture_draft_and_updates_tags_and_size(app, config):
    runtime = Runtime(app, config.output_file)
    runtime.configure(config, None)
    runtime.capture.editor.setPlainText("keep")
    runtime.show_browse()
    candidate = replace(config, theme="light", window_size="wide", tags={"research": {"emoji": "R", "color": "#abcdef"}})
    assert runtime.can_apply_config(candidate) is None
    runtime.apply_config(candidate)
    assert runtime.capture.editor.toPlainText() == "keep"
    assert runtime.capture.width() == 520
    assert "research" in runtime.capture.editor.tags
    assert runtime.browse.tags.findData("research") >= 0
    assert runtime.browse.delegate.colors == settings.THEMES["light"]
    runtime.shutdown()


def test_runtime_blocks_path_change_during_drafts_and_clears_undo(app, config, tmp_path):
    runtime = Runtime(app, config.output_file)
    candidate = replace(config, output_file=tmp_path / "another.md")
    runtime.capture.editor.setPlainText("draft")
    assert "capture draft" in runtime.can_apply_config(candidate)
    runtime.capture.editor.clear()
    assert runtime.can_apply_config(candidate) is None
    runtime.browse._undo = (None, [], [])
    runtime.apply_config(candidate)
    assert runtime.capture.notes_path == candidate.output_file
    assert runtime.browse.notes_path == candidate.output_file
    assert runtime.browse._undo is None
    runtime.shutdown()


def test_runtime_settings_reuse_cancel_and_quit_protection(app, config, monkeypatch):
    runtime = Runtime(app, config.output_file)
    runtime.configure(config, None)
    runtime.show_settings()
    dialog = runtime._settings
    runtime.show_settings()
    assert runtime._settings is dialog
    dialog.theme.setCurrentText("dracula")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    runtime.request_quit()
    assert not runtime.closed and dialog.isVisible()
    dialog.reject()
    assert runtime._settings is None
    assert runtime.theme == "tokyo-night"
    runtime.shutdown()


@pytest.mark.parametrize("theme", list(settings.THEMES))
def test_settings_tabs_render_and_escape_cancels(app, config, theme):
    apply_theme(app, theme)
    config.theme = theme
    dialog = settings.SettingsDialog(config, None, lambda value: pytest.fail("Unexpected save"))
    dialog.show()
    for tab in range(dialog.tabs.count()):
        dialog.tabs.setCurrentIndex(tab)
        app.processEvents()
        assert not dialog.grab().isNull()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()


def test_main_requires_explicit_destination(monkeypatch):
    from cogstash.ui.qt.__main__ import main
    monkeypatch.setattr(sys, "argv", ["qt"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_main_reads_existing_config_and_applies_explicit_overrides(config, tmp_path, monkeypatch):
    from cogstash.ui.qt import app as application
    from cogstash.ui.qt.__main__ import main
    path = tmp_path / "settings.json"
    save_config(config, path)
    calls = []
    monkeypatch.setattr(application, "run", lambda *args: calls.append(args) or 0)
    monkeypatch.setattr(sys, "argv", ["qt", "--config", str(path), "--theme", "light", "--no-hotkey"])
    assert main() == 0
    assert calls[0][2:4] == ("light", False)
    assert calls[0][-1] == path
    assert settings.read_config(path).theme == "tokyo-night"


def test_custom_tag_is_rendered_when_capturing(app, config):
    runtime = Runtime(app, config.output_file)
    runtime.configure(replace(config, tags={"research": {"emoji": "R", "color": "#abcdef"}}), None)
    runtime.capture.editor.setPlainText("Read this #research")
    runtime.capture.save_note()
    assert "R Read this #research" in config.output_file.read_text(encoding="utf-8")
    runtime.shutdown()


def test_new_config_defaults_to_sibling_notes_without_creating_files(tmp_path, monkeypatch):
    from cogstash.ui.qt import app as application
    from cogstash.ui.qt.__main__ import main
    path = tmp_path / "prototype.json"
    calls = []
    monkeypatch.setattr(application, "run", lambda *args: calls.append(args) or 0)
    monkeypatch.setattr(sys, "argv", ["qt", "--config", str(path), "--no-hotkey"])
    assert main() == 0
    assert calls[0][0] == tmp_path / "prototype.notes.md"
    assert not path.exists()
    assert not calls[0][0].exists()


def test_settings_path_change_during_note_edit_is_blocked_before_persistence(app, config, tmp_path):
    config.output_file.write_text("- [2026-01-01 12:00] saved note\n", encoding="utf-8")
    path = tmp_path / "settings.json"
    save_config(config, path)
    runtime = Runtime(app, config.output_file)
    runtime.configure(config, path)
    runtime.browse.edit_selected()
    runtime.show_settings()
    runtime._settings.notes.setText(str(tmp_path / "new.md"))
    baseline = path.read_bytes()
    runtime._settings.save()
    assert "Finish or cancel" in runtime._settings.error.text()
    assert path.read_bytes() == baseline
    assert runtime.notes == config.output_file
    runtime.shutdown()
