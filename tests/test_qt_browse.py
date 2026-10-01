from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QStyleOptionViewItem

from cogstash.core import MutationStatus, parse_notes
from cogstash.ui.qt import browse as module
from cogstash.ui.ui_shared import THEMES


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def window(app, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text(
        "- [2026-10-01 10:00] ☐ first #todo #work\n  continuation\n"
        "- [2026-10-01 10:00] second #idea\n"
        "- [2026-10-02 11:00] ☑ third #todo\n", encoding="utf-8",
    )
    widget = module.BrowseWindow(path)
    yield widget
    if widget._edit_dialog is not None:
        widget._edit_dialog.reject()
    widget.hide()
    widget.deleteLater()
    app.processEvents()


def choose(window, fragment):
    row = next(i for i, note in enumerate(window.model.notes) if fragment in note.text)
    window.view.setCurrentIndex(window.model.index(row, 0))
    return window.selected_note()


def test_search_tag_clear_empty_and_counts(window):
    window.tags.setCurrentIndex(window.tags.findData("todo"))
    window.search.setText("FIRST WORK")
    assert window.model.rowCount() == 1
    assert "#todo" in window.filter_summary.text()
    assert "Search: FIRST WORK" in window.filter_summary.text()
    assert window.tags.currentText() == "#todo (2)"
    window.search.setText("not present")
    assert window.model.rowCount() == 0
    assert "No notes match" in window.empty.text()
    assert not any(action.isEnabled() for action in window.note_actions.values())
    window.clear_filters()
    assert window.model.rowCount() == 3
    assert not window.clear_button.isEnabled()


def test_edit_multiline_preserves_timestamp_and_refreshes_positions(window):
    note = choose(window, "first")
    assert window.edit(note, "edited #idea\nmore\nlines") is MutationStatus.SUCCESS
    assert window.selected_note().text == "edited #idea\nmore\nlines"
    parsed = parse_notes(window.notes_path)
    assert parsed[0].timestamp == note.timestamp
    assert parsed[0].tags == ["idea"]
    second = choose(window, "second")
    assert second.line_number == 3
    assert window.delete(second) is MutationStatus.SUCCESS
    assert [n.text for n in parse_notes(window.notes_path)] == ["edited #idea\nmore\nlines", "☑ third #todo"]


def test_mark_done_refreshes_and_disables_action(window):
    choose(window, "first")
    assert window.note_actions["Mark done"].isEnabled()
    window.mark_selected_done()
    assert window.selected_note().text.startswith("☑ first")
    updated = choose(window, "first")
    assert updated.is_done
    assert "marked done" in window.notice.text()
    assert not window.note_actions["Mark done"].isEnabled()


def test_same_timestamp_external_change_is_stale_and_never_overwritten(window):
    note = choose(window, "second")
    updated = window.notes_path.read_text(encoding="utf-8").replace("second #idea", "someone else's update #idea")
    window.notes_path.write_text(updated, encoding="utf-8")
    assert window.edit(note, "overwrite") is MutationStatus.STALE_NOTE
    assert window.notes_path.read_text(encoding="utf-8") == updated
    assert "changed on disk" in window.notice.text()
    assert any("someone else's" in n.text for n in window.model.notes)


@pytest.mark.parametrize("result,message", [
    (MutationStatus.IO_ERROR, "Could not update"),
    (MutationStatus.STALE_NOTE, "changed on disk"),
    (MutationStatus.INVALID_INPUT, "cannot be empty"),
])
def test_failed_edit_retains_dialog_input(window, monkeypatch, result, message):
    choose(window, "second")
    before = window.notes_path.read_text(encoding="utf-8")
    monkeypatch.setattr(module, "edit_note", lambda *args: result)
    window.edit_selected()
    dialog = window._edit_dialog
    dialog.editor.setPlainText("keep my draft")
    dialog.save(window, choose(window, "second"))
    assert dialog.editor.toPlainText() == "keep my draft"
    assert message in dialog.error.text()
    assert window._edit_dialog is dialog
    assert window.notes_path.read_text(encoding="utf-8") == before


def test_already_done_status_does_not_claim_success(window, monkeypatch):
    choose(window, "first")
    monkeypatch.setattr(module, "mark_done", lambda *a: MutationStatus.ALREADY_DONE)
    window.mark_selected_done()
    assert window.notice.text() == "Note already done."


def test_delete_preview_is_plain_text_and_cancellation_keeps_note(window, monkeypatch):
    choose(window, "second")
    before = window.notes_path.read_text(encoding="utf-8")
    seen = []

    def cancel(dialog):
        seen.append((dialog.text(), dialog.textFormat(), dialog.defaultButton().text()))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", cancel)
    window.delete_selected()
    assert "second #idea" in seen[0][0]
    assert seen[0][1] == Qt.TextFormat.PlainText
    assert window.notes_path.read_text(encoding="utf-8") == before
    note = choose(window, "first")
    note.text = "x" * 300 + "\nline2\nline3\nline4"
    assert len(window.delete_preview(note)) <= 180
    assert window.delete_preview(note).endswith("...")


def test_delete_undo_roundtrip_and_single_use(window):
    before = window.notes_path.read_text(encoding="utf-8")
    note = choose(window, "first")
    assert window.delete(note) is MutationStatus.SUCCESS
    assert len(parse_notes(window.notes_path)) == 2
    window.undo_delete()
    assert window.notes_path.read_text(encoding="utf-8") == before
    assert not window.undo_button.isEnabled()
    window.undo_delete()
    assert window.notes_path.read_text(encoding="utf-8") == before


def test_undo_preserves_appended_notes(window):
    before = window.notes_path.read_text(encoding="utf-8")
    window.delete(choose(window, "second"))
    tail = "- [2026-10-02 12:00] appended later\n"
    with window.notes_path.open("a", encoding="utf-8") as stream:
        stream.write(tail)
    window.undo_delete()
    assert window.notes_path.read_text(encoding="utf-8") == before + tail


def test_undo_refuses_conflicting_changes_and_preserves_retry(window):
    window.delete(choose(window, "second"))
    changed = window.notes_path.read_text(encoding="utf-8").replace("first", "changed externally")
    window.notes_path.write_text(changed, encoding="utf-8")
    window.undo_delete()
    assert window.notes_path.read_text(encoding="utf-8") == changed
    assert "cannot safely restore" in window.notice.text()
    assert window.undo_button.isEnabled()


def test_failed_undo_can_be_retried(window, monkeypatch):
    before = window.notes_path.read_text(encoding="utf-8")
    window.delete(choose(window, "first"))
    original = module._atomic_write

    def fail(*args):
        raise OSError("blocked")

    monkeypatch.setattr(module, "_atomic_write", fail)
    window.undo_delete()
    assert window.undo_button.isEnabled()
    assert "Could not restore" in window.notice.text()
    monkeypatch.setattr(module, "_atomic_write", original)
    window.undo_delete()
    assert window.notes_path.read_text(encoding="utf-8") == before


def test_keyboard_copy_and_repeated_edit_reuses_dialog(window, app):
    window.show()
    window.view.setFocus()
    choose(window, "second")
    app.processEvents()
    QTest.keyClick(window.view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert app.clipboard().text() == "second #idea"
    QTest.keyClick(window.view, Qt.Key.Key_F2)
    first = window._edit_dialog
    assert first is not None
    window.edit_selected()
    assert window._edit_dialog is first


@pytest.mark.parametrize("theme", list(THEMES))
def test_card_rendering_size_and_accessible_done_state(app, tmp_path, theme):
    path = tmp_path / "notes.md"
    path.write_text("- [2026-10-02 12:00] ☑ multiline #todo\n  next line 世界\n", encoding="utf-8")
    window = module.BrowseWindow(path, theme=theme)
    window.show()
    app.processEvents()
    option = QStyleOptionViewItem()
    option.initFrom(window.view)
    option.rect = QRect(0, 0, 300, 0)
    index = window.model.index(0, 0)
    assert "Completed" in index.data(Qt.ItemDataRole.AccessibleTextRole)
    assert window.delegate.sizeHint(option, index).height() > 80
    rendered = window.grab()
    assert isinstance(rendered, QPixmap) and not rendered.isNull()
    window.close()
    window.deleteLater()


def test_cards_fit_viewport_after_scrollbar_and_resize(window, app):
    window.show()
    for width in (760, 420, 1000):
        window.resize(width, 480)
        app.processEvents()
        window.view.doItemsLayout()
        app.processEvents()
        rect = window.view.visualRect(window.model.index(0, 0))
        assert rect.width() <= window.view.viewport().width()
        assert window.view.horizontalScrollBar().maximum() == 0
        assert len(window.delegate.heights) <= window.model.rowCount()


def test_closing_browse_can_keep_unsaved_edit(window, monkeypatch):
    window.show()
    window.edit_selected()
    dialog = window._edit_dialog
    dialog.editor.setPlainText("unsaved edit")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.close()
    assert window.isVisible()
    assert window._edit_dialog is dialog
    assert dialog.editor.toPlainText() == "unsaved edit"
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    window.close()
    assert not window.isVisible()
    assert window._edit_dialog is None


def test_runtime_quit_respects_unsaved_edit(app, tmp_path, monkeypatch):
    from cogstash.ui.qt.runtime import Runtime

    path = tmp_path / "notes.md"
    path.write_text("- [2026-10-02 12:00] original\n", encoding="utf-8")
    runtime = Runtime(app, path)
    runtime.show_browse()
    runtime.browse.edit_selected()
    runtime.browse._edit_dialog.editor.setPlainText("pending")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    runtime.request_quit()
    assert not runtime.closed
    runtime.browse._edit_dialog.reject()
    runtime.shutdown()
    runtime.deleteLater()


def test_escape_closes_browse(window, app):
    window.show()
    window.view.setFocus()
    app.processEvents()
    QTest.keyClick(window.view, Qt.Key.Key_Escape)
    assert not window.isVisible()


def test_edit_filtered_out_does_not_select_a_different_note(window):
    window.search.setText("first")
    note = window.selected_note()
    assert window.edit(note, "different text") is MutationStatus.SUCCESS
    assert window.selected_note() is None
    assert "no longer matches" in window.notice.text()
    assert not window.note_actions["Delete"].isEnabled()
