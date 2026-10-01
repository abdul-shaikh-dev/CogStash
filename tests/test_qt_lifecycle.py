from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from cogstash.ui.qt.app import CaptureWindow
from cogstash.ui.qt.hotkeys import HotkeyAdapter
from cogstash.ui.qt.runtime import Runtime


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def runtime(app, tmp_path):
    instance = Runtime(app, tmp_path / "notes.md")
    yield instance
    instance.shutdown()
    instance.deleteLater()
    app.processEvents()


@pytest.fixture
def listeners(monkeypatch):
    created = []

    class Listener:
        def __init__(self, bindings):
            self.callback = next(iter(bindings.values()))
            self.alive = False
            self.stops = 0
            self.error = None
            created.append(self)

        def start(self):
            self.alive = True

        def stop(self):
            self.stops += 1
            self.alive = False

        def is_alive(self):
            return self.alive

        def join(self, timeout):
            if self.error:
                raise self.error

    monkeypatch.setitem(sys.modules, "pynput.keyboard", SimpleNamespace(GlobalHotKeys=Listener))
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    return created


def test_windows_are_lazy_reused_and_capture_events_are_queued(runtime, app, monkeypatch):
    assert runtime._capture is None and runtime._browse is None
    seen = []
    original = CaptureWindow.reveal

    def reveal(window):
        seen.append(QThread.currentThread())
        original(window)

    monkeypatch.setattr(CaptureWindow, "reveal", reveal)
    worker = threading.Thread(target=runtime.capture_requested.emit)
    worker.start()
    worker.join()
    assert runtime._capture is None
    app.processEvents()
    window = runtime.capture
    assert seen == [app.thread()]
    window.editor.setPlainText("retained")
    window.close()
    runtime.show_capture()
    assert runtime.capture is window
    assert window.editor.toPlainText() == "retained"
    assert runtime._browse is None
    runtime.show_browse()
    browse = runtime.browse
    runtime.show_browse()
    assert runtime.browse is browse


def test_no_duplicate_listener_and_no_reopen_after_shutdown(runtime, app, listeners):
    runtime.start_hotkey("<ctrl>+j")
    runtime.start_hotkey("<ctrl>+k")
    assert len(listeners) == 1
    listeners[0].callback()
    runtime.shutdown()
    app.processEvents()
    assert runtime._capture is None
    assert listeners[0].stops == 1
    assert not runtime.hotkeys.timer.isActive()
    runtime.start_hotkey("<ctrl>+j")
    runtime.shutdown()
    assert len(listeners) == 1


def test_late_listener_failure_opens_actionable_fallback(runtime, app, listeners):
    runtime.start_hotkey("<ctrl>+j")
    listeners[0].alive = False
    listeners[0].error = RuntimeError("lost keyboard hook")
    runtime.hotkeys.check_health()
    app.processEvents()
    assert "lost keyboard hook" in runtime.warning_text
    assert runtime.browse.isVisible()
    assert runtime.hotkeys.listener is None
    runtime.show_capture()
    assert runtime.capture.isVisible()


def test_shutdown_still_hides_windows_when_listener_join_raises(runtime, listeners):
    runtime.start_hotkey("<ctrl>+j")
    listeners[0].error = RuntimeError("listener failed")
    runtime.show_capture()
    runtime.shutdown()
    assert not runtime.capture.isVisible()
    assert not runtime.tray.isVisible()
    assert runtime.hotkeys.listener is None


def test_wayland_uses_manual_fallback_without_starting_listener(runtime, app, listeners, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    runtime.start_hotkey("<ctrl>+j")
    app.processEvents()
    assert not listeners
    assert "Wayland" in runtime.warning_text
    assert runtime.browse.isVisible()


def test_start_failure_cleans_up_partially_started_listener(app, listeners, monkeypatch):
    from pynput.keyboard import GlobalHotKeys

    def fail_start(listener):
        listener.alive = True
        raise RuntimeError("partial startup")

    monkeypatch.setattr(GlobalHotKeys, "start", fail_start)
    adapter = HotkeyAdapter()
    failures = []
    adapter.failed.connect(failures.append)
    adapter.start("<ctrl>+j")
    assert listeners[0].stops == 1
    assert adapter.listener is None
    assert "partial startup" in failures[0]
    adapter.shutdown()


def test_browse_close_hides_with_tray_and_requests_quit_without(runtime, monkeypatch):
    requested = []
    monkeypatch.setattr(runtime, "request_quit", lambda: requested.append(True))
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    runtime.show_browse()
    runtime.browse.close()
    assert not runtime.browse.isVisible()
    assert not requested
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    runtime.show_browse()
    runtime.browse.close()
    assert requested == [True]


def test_quit_cancellation_preserves_draft(runtime, monkeypatch):
    runtime.capture.editor.setPlainText("unsaved")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    runtime.request_quit()
    assert not runtime.closed
    assert runtime.capture.isVisible()
    assert runtime.capture.editor.toPlainText() == "unsaved"
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    runtime.request_quit()
    assert runtime.closed


def test_tag_completion_enter_then_save_and_unicode_cursor(app, tmp_path):
    window = CaptureWindow(tmp_path / "notes.md")
    window.reveal()
    window.editor.setPlainText("😀 #id")
    window.editor.moveCursor(window.editor.textCursor().MoveOperation.End)
    app.processEvents()
    assert window.editor.suggestions.isVisible()
    QTest.keyClick(window.editor, Qt.Key.Key_Return)
    assert window.editor.toPlainText() == "😀 #idea"
    assert not window.notes_path.exists()
    QTest.keyClick(window.editor, Qt.Key.Key_Return)
    assert window.notes_path.exists()
    assert not window.isVisible()


def test_escape_dismisses_suggestions_before_capture_and_shift_enter_keeps_newline(app, tmp_path):
    window = CaptureWindow(tmp_path / "notes.md")
    window.reveal()
    QTest.keyClicks(window.editor, "#i")
    assert window.editor.suggestions.isVisible()
    QTest.keyClick(window.editor, Qt.Key.Key_Escape)
    assert window.isVisible()
    assert not window.editor.suggestions.isVisible()
    QTest.keyClick(window.editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert window.editor.toPlainText() == "#i\n"
    QTest.keyClick(window.editor, Qt.Key.Key_Escape)
    assert not window.isVisible()


@pytest.mark.parametrize("preset,width", [("compact", 320), ("default", 400), ("wide", 520)])
def test_capture_size_preset_and_growth_limit(app, tmp_path, preset, width):
    window = CaptureWindow(tmp_path / "notes.md", window_size=preset)
    assert window.width() == width
    small = window.editor.height()
    window.editor.setPlainText("line\n" * 30)
    tall = window.editor.height()
    assert tall > small
    window.editor.setPlainText("line\n" * 60)
    assert window.editor.height() == tall
    window.hide()


def test_tag_navigation_tab_and_click(app, tmp_path):
    window = CaptureWindow(tmp_path / "notes.md")
    window.reveal()
    QTest.keyClicks(window.editor, "#")
    QTest.keyClick(window.editor, Qt.Key.Key_Down)
    expected = window.editor.suggestions.currentItem().data(Qt.ItemDataRole.UserRole)
    QTest.keyClick(window.editor, Qt.Key.Key_Tab)
    assert window.editor.toPlainText() == "#" + expected
    window.editor.clear()
    QTest.keyClicks(window.editor, "#")
    item = window.editor.suggestions.item(0)
    expected = item.data(Qt.ItemDataRole.UserRole)
    QTest.mouseClick(window.editor.suggestions.viewport(), Qt.MouseButton.LeftButton,
                     pos=window.editor.suggestions.visualItemRect(item).center())
    assert window.editor.toPlainText() == "#" + expected
    window.hide()


def test_open_notes_routes_to_desktop_service_and_reports_missing(runtime, app, monkeypatch):
    from cogstash.ui.qt.runtime import QDesktopServices

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    runtime.open_notes()
    assert not opened
    assert "Save a note first" in runtime.warning_text
    runtime.notes.write_text("note", encoding="utf-8")
    runtime.open_notes()
    assert Path(opened[0]) == runtime.notes.resolve()


def test_application_quit_discards_confirmed_draft_and_exits(runtime, app, monkeypatch):
    runtime.show_browse()
    runtime.show_capture()
    runtime.capture.editor.setPlainText("draft")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: app.exit(99))
    timeout.start(2000)
    QTimer.singleShot(0, app.quit)
    try:
        assert app.exec() == 0
        assert runtime.closed
    finally:
        timeout.stop()


def test_macos_permission_check_does_not_reject_before_thread_initializes(runtime, app, listeners, monkeypatch):
    from pynput.keyboard import GlobalHotKeys

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(GlobalHotKeys, "IS_TRUSTED", False, raising=False)
    runtime.start_hotkey("<ctrl>+j")
    assert listeners[0].alive
    listeners[0].alive = False
    runtime.hotkeys.check_health()
    app.processEvents()
    assert "Accessibility" in runtime.warning_text


def test_shutdown_retries_stop_after_startup_race(runtime, listeners, monkeypatch):
    runtime.start_hotkey("<ctrl>+j")
    listener = listeners[0]

    def delayed_stop():
        listener.stops += 1
        if listener.stops > 1:
            listener.alive = False

    monkeypatch.setattr(listener, "stop", delayed_stop)
    runtime.shutdown()
    assert listener.stops == 2
    assert not listener.alive
    assert runtime.hotkeys.listener is None


@pytest.mark.parametrize("failure_stage", ["hotkey", "browse"])
def test_entrypoint_cleans_up_if_startup_raises(monkeypatch, tmp_path, failure_stage):
    from cogstash.ui.qt import app as ui
    from cogstash.ui.qt import runtime as lifecycle

    events = []
    fake_app = SimpleNamespace(setQuitOnLastWindowClosed=lambda value: None, setStyleSheet=lambda value: None)

    def stage(name):
        events.append(name)
        if name == failure_stage:
            raise RuntimeError("startup failed")

    fake_runtime = SimpleNamespace(
        start_hotkey=lambda binding: stage("hotkey"), show_browse=lambda: stage("browse"),
        shutdown=lambda: events.append("cleanup"),
    )
    monkeypatch.setattr(ui, "QApplication", lambda args: fake_app)
    monkeypatch.setattr(lifecycle, "Runtime", lambda *args: fake_runtime)
    with pytest.raises(RuntimeError, match="startup failed"):
        ui.run(tmp_path / "notes.md", "<ctrl>+j", "light", True)
    assert events[-1] == "cleanup"
