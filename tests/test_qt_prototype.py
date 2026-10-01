from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from cogstash.core import parse_notes
from cogstash.ui.qt.app import BrowseWindow, CaptureWindow
from cogstash.ui.qt.runtime import Runtime


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_capture_keyboard_and_roundtrip(app, tmp_path):
    path = tmp_path / "notes.md"
    window = CaptureWindow(path)
    window.reveal()
    window.editor.setPlainText("Hello #idea")
    window.editor.moveCursor(window.editor.textCursor().MoveOperation.End)
    QTest.keyClick(window.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    window.editor.insertPlainText("世界")
    QTest.keyClick(window.editor, Qt.Key.Key_Return)
    assert not window.isVisible()
    assert window.editor.toPlainText() == ""
    assert parse_notes(path)[0].text.endswith("Hello #idea\n世界")


def test_failure_and_escape_retain_draft(app, tmp_path):
    window = CaptureWindow(tmp_path)  # A directory cannot receive an appended note.
    window.reveal()
    window.editor.setPlainText("Keep this draft")
    window.save_note()
    assert window.isVisible()
    assert "Could not save" in window.status.text()
    QTest.keyClick(window.editor, Qt.Key.Key_Escape)
    window.reveal()
    assert window.editor.toPlainText() == "Keep this draft"
    window.hide()


def test_long_note_is_not_silently_truncated(app, tmp_path):
    path = tmp_path / "notes.md"
    window = CaptureWindow(path)
    window.editor.setPlainText("x" * 10_001)
    window.save_note()
    assert not path.exists()
    assert len(window.editor.toPlainText()) == 10_001


def test_browse_filter_and_refresh(app, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("- [2026-01-01 10:00] older #todo\n- [2026-01-02 10:00] newer #idea\n", encoding="utf-8")
    window = BrowseWindow(path)
    assert window.model.notes[0].text == "newer #idea"
    window.search.setText("older TODO")
    assert window.model.rowCount() == 1
    path.write_text("", encoding="utf-8")
    window.reload()
    assert window.model.rowCount() == 0


def test_runtime_queued_capture_and_save_refresh(app, tmp_path):
    runtime = Runtime(app, tmp_path / "notes.md")
    runtime.capture_requested.emit()
    app.processEvents()
    assert runtime.capture.isVisible()
    runtime.capture.editor.setPlainText("from runtime")
    runtime.capture.save_note()
    assert runtime.browse.model.rowCount() == 1
    runtime.shutdown()
    runtime.shutdown()
    runtime.browse.hide()


def test_invalid_note_file_shows_error(app, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("- [2026-99-99 10:00] invalid date\n", encoding="utf-8")
    window = BrowseWindow(path)
    assert "Could not read" in window.status.text()


def test_hotkey_failure_keeps_manual_capture_available(app, tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    def fail(_bindings):
        raise ValueError("invalid binding")

    monkeypatch.setitem(sys.modules, "pynput.keyboard", SimpleNamespace(GlobalHotKeys=fail))
    runtime = Runtime(app, tmp_path / "notes.md")
    runtime.start_hotkey("invalid")
    assert runtime.hotkeys.listener is None
    app.processEvents()
    assert "Global hotkey unavailable" in runtime.warning.text()
    runtime.capture.reveal()
    assert runtime.capture.isVisible()
    runtime.capture.hide()
    runtime.shutdown()
