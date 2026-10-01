"""Qt Browse with model-backed cards and file-backed note actions."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QKeyEvent, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from cogstash.core import (
    DEFAULT_SMART_TAGS,
    MutationStatus,
    Note,
    count_tags,
    delete_note,
    edit_note,
    filter_by_tag,
    mark_done,
    parse_notes,
    search_notes,
)
from cogstash.core.notes import _atomic_write
from cogstash.ui.ui_shared import THEMES


class NoteModel(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self.notes: list[Note] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.notes)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self.notes):
            return None
        note = self.notes[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            state = "Completed" if note.is_done else "Open todo" if "todo" in note.tags else "Note"
            return f"{note.timestamp:%d %b %Y  %H:%M} · {state}\n{note.text}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return note.text
        if role == Qt.ItemDataRole.UserRole:
            return note
        return None

    def replace(self, notes: list[Note]) -> None:
        self.beginResetModel()
        self.notes = notes
        self.endResetModel()


class NoteDelegate(QStyledItemDelegate):
    """Paint cards without allocating a widget tree for every note."""

    def __init__(self, view: QListView, theme: str) -> None:
        super().__init__(view)
        self.view = view
        self.colors = THEMES[theme]
        self.heights: dict[tuple[int, int, str], int] = {}
        self.cache_layout: tuple[int, str] | None = None

    def text_width(self, option: QStyleOptionViewItem) -> int:
        return max(40, min(option.rect.width() or self.view.viewport().width(), self.view.viewport().width()) - 32)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        note = index.data(Qt.ItemDataRole.UserRole)
        width = self.text_width(option)
        layout = (width, option.font.toString())
        if layout != self.cache_layout:
            self.heights.clear()
            self.cache_layout = layout
        key = (index.row(), *layout)
        if key not in self.heights:
            metrics = QFontMetrics(option.font)
            body = metrics.boundingRect(QRect(0, 0, width, 1_000_000), (Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere), note.text).height()
            tags = "  ".join("#" + tag for tag in note.tags)
            tag_height = metrics.boundingRect(QRect(0, 0, width, 1_000_000), (Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere), tags).height() if tags else 0
            self.heights[key] = 40 + metrics.height() + body + (tag_height + 8 if tags else 0)
        return QSize(0, self.heights[key])

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        note = index.data(Qt.ItemDataRole.UserRole)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        colors = self.colors
        accent = QColor(colors["accent"])
        channels = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                    for value in (accent.redF(), accent.greenF(), accent.blueF())]
        luminance = sum(value * weight for value, weight in zip(channels, (0.2126, 0.7152, 0.0722)))
        selection_text = "#000000" if luminance > 0.179 else "#ffffff"
        foreground = QColor(selection_text if selected else colors["fg"])
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = option.rect.adjusted(3, 3, -3, -5)
        painter.setBrush(QColor(colors["accent"] if selected else colors["entry_bg"]))
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        painter.setPen(QPen(QColor(colors["fg"] if focused else colors["muted"]), 2 if focused else 1))
        painter.drawRoundedRect(card, 6, 6)
        painter.setPen(foreground)
        painter.setFont(option.font)
        metrics = QFontMetrics(option.font)
        x, y, width = option.rect.x() + 16, option.rect.y() + 14, self.text_width(option)
        state = " · Completed" if note.is_done else " · Open todo" if "todo" in note.tags else ""
        painter.drawText(QRect(x, y, width, metrics.height()), Qt.AlignmentFlag.AlignLeft, f"{note.timestamp:%d %b %Y  %H:%M}{state}")
        y += metrics.height() + 8
        body_height = metrics.boundingRect(QRect(0, 0, width, 1_000_000), (Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere), note.text).height()
        font = QFont(option.font)
        font.setStrikeOut(note.is_done)
        painter.setFont(font)
        painter.drawText(QRect(x, y, width, body_height), (Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere), note.text)
        if note.tags:
            painter.setFont(option.font)
            painter.drawText(QRect(x, y + body_height + 8, width, option.rect.height()), (Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere),
                             "  ".join("#" + tag for tag in note.tags))
        painter.restore()


class EditDialog(QDialog):
    def __init__(self, owner: BrowseWindow, note: Note) -> None:
        super().__init__(owner)
        self.original_text = note.text
        self.setWindowTitle("Edit note")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(520, 340)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(note.timestamp.strftime("%d %b %Y  %H:%M")))
        self.editor = QPlainTextEdit(note.text)
        self.editor.setAccessibleName("Edit note text")
        layout.addWidget(self.editor)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(lambda: self.save(owner, note))
        layout.addWidget(buttons)

    def save(self, owner: BrowseWindow, note: Note) -> None:
        result = owner.edit(note, self.editor.toPlainText())
        if result is MutationStatus.SUCCESS:
            self.accept()
        else:
            self.error.setText(owner.notice.text())


class BrowseWindow(QWidget):
    close_requested = Signal()

    def __init__(self, notes_path: Path, managed: bool = False, theme: str = "tokyo-night") -> None:
        super().__init__()
        self.notes_path = notes_path
        self.managed = managed
        self.notes: list[Note] = []
        self.read_error = ""
        self._edit_dialog: EditDialog | None = None
        self._undo: tuple[Note, list[str], list[str]] | None = None
        self.setWindowTitle("CogStash · Browse")
        self.resize(760, 620)
        self.setMinimumSize(360, 360)
        layout = QVBoxLayout(self)
        title = QLabel("Your notes")
        title.setObjectName("heading")
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your notes…")
        self.search.setAccessibleName("Search notes")
        layout.addWidget(self.search)
        filter_row = QHBoxLayout()
        self.tags = QComboBox()
        self.tags.setAccessibleName("Filter by tag")
        filter_row.addWidget(self.tags)
        self.clear_button = QPushButton("Clear filters")
        self.clear_button.clicked.connect(self.clear_filters)
        filter_row.addWidget(self.clear_button)
        layout.addLayout(filter_row)
        self.filter_summary = QLabel()
        self.filter_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.filter_summary.setWordWrap(True)
        layout.addWidget(self.filter_summary)
        self.model = NoteModel()
        self.view = QListView()
        self.view.setAccessibleName("Notes")
        self.view.setModel(self.model)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.delegate = NoteDelegate(self.view, theme)
        self.view.setItemDelegate(self.delegate)
        self.model.modelReset.connect(self.delegate.heights.clear)
        layout.addWidget(self.view)
        self.empty = QLabel()
        self.empty.setTextFormat(Qt.TextFormat.PlainText)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notice = QLabel()
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        action_row = QHBoxLayout()
        self.note_actions: dict[str, QAction] = {}
        for name, shortcut, callback in (
            ("Edit", "F2", self.edit_selected), ("Mark done", "Ctrl+D", self.mark_selected_done),
            ("Delete", "Delete", self.delete_selected), ("Copy text", "Ctrl+C", self.copy_selected),
        ):
            action = QAction(name, self.view)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
            action.triggered.connect(callback)
            self.view.addAction(action)
            self.note_actions[name] = action
            button = QPushButton(name)
            button.setAccessibleName(name + " selected note")
            button.clicked.connect(action.trigger)
            action.changed.connect(lambda a=action, b=button: b.setEnabled(a.isEnabled()))
            action_row.addWidget(button)
        layout.addLayout(action_row)
        self.action_row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        self.action_row.addWidget(refresh)
        self.undo_button = QPushButton("Undo delete")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_delete)
        self.action_row.addWidget(self.undo_button)
        layout.addLayout(self.action_row)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.edit_selected)
        self.view.selectionModel().currentChanged.connect(self.update_actions)
        self.search.textChanged.connect(self.apply_filter)
        self.tags.currentIndexChanged.connect(self.apply_filter)
        self.reload()

    def selected_note(self) -> Note | None:
        index = self.view.currentIndex()
        return self.model.notes[index.row()] if index.isValid() and index.row() < len(self.model.notes) else None

    @Slot()
    def update_actions(self) -> None:
        note = self.selected_note()
        for name, action in self.note_actions.items():
            action.setEnabled(note is not None and (name != "Mark done" or ("todo" in note.tags and not note.is_done)))

    @Slot()
    def reload(self) -> None:
        self.read_error = ""
        try:
            self.notes = sorted(parse_notes(self.notes_path), key=lambda n: (n.timestamp, n.index), reverse=True)
        except (OSError, ValueError, UnicodeError) as exc:
            self.notes = []
            self.read_error = f"Could not read notes: {exc}"
        tag = self.tags.currentData()
        counts = count_tags(self.notes)
        names = list(dict.fromkeys([*DEFAULT_SMART_TAGS, *counts, *([tag] if tag else [])]))
        self.tags.blockSignals(True)
        self.tags.clear()
        self.tags.addItem("All tags", None)
        for name in names:
            self.tags.addItem(f"#{name} ({counts.get(name, 0)})", name)
        self.tags.setCurrentIndex(max(0, self.tags.findData(tag)))
        self.tags.blockSignals(False)
        self.apply_filter()

    @Slot()
    def apply_filter(self) -> None:
        selected = self.selected_note()
        notes = search_notes(self.notes, self.search.text())
        tag = self.tags.currentData()
        if tag:
            notes = filter_by_tag(notes, tag)
        self.model.replace(notes)
        row = notes.index(selected) if selected in notes else 0
        if notes:
            self.view.setCurrentIndex(self.model.index(row, 0))
        filters = []
        if self.search.text().strip():
            filters.append(f"Search: {self.search.text().strip()}")
        if tag:
            filters.append(f"Tag: #{tag}")
        self.filter_summary.setText(" · ".join(filters))
        self.filter_summary.setVisible(bool(filters))
        self.clear_button.setEnabled(bool(filters))
        empty = self.read_error or ("No notes match these filters." if filters else "No notes yet. Capture your first thought.")
        self.empty.setText(empty)
        self.empty.setVisible(not notes)
        open_todos = sum("todo" in n.tags and not n.is_done for n in self.notes)
        todo_label = "todo" if open_todos == 1 else "todos"
        self.status.setText(self.read_error or f"{len(notes)} of {len(self.notes)} notes · {open_todos} open {todo_label}")
        self.update_actions()

    @Slot()
    def clear_filters(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.tags.blockSignals(True)
        self.tags.setCurrentIndex(0)
        self.tags.blockSignals(False)
        self.apply_filter()

    def perform(self, note: Note, operation: Callable[[], MutationStatus]) -> MutationStatus:
        try:
            current = parse_notes(self.notes_path)
            # Core's timestamp check alone cannot distinguish notes saved in the same minute.
            fresh = any(n.line_number == note.line_number and n.timestamp == note.timestamp and n.text == note.text for n in current)
            result = operation() if fresh else MutationStatus.STALE_NOTE
        except (OSError, ValueError, UnicodeError):
            result = MutationStatus.IO_ERROR
        if result is MutationStatus.STALE_NOTE:
            self.reload()
            self.notice.setText("Notes changed on disk. Reloaded; select the note again.")
        elif result is MutationStatus.IO_ERROR:
            self.notice.setText("Could not update notes. Check the file and try again.")
        elif result is MutationStatus.INVALID_INPUT:
            self.notice.setText("Note text cannot be empty.")
        elif result is MutationStatus.ALREADY_DONE:
            self.reload()
            self.notice.setText("Note already done.")
        return result

    def select_note(self, original: Note, text: str) -> bool:
        for row, note in enumerate(self.model.notes):
            if note.line_number == original.line_number and note.timestamp == original.timestamp and note.text == text:
                self.view.setCurrentIndex(self.model.index(row, 0))
                return True
        self.view.setCurrentIndex(QModelIndex())
        self.update_actions()
        return False

    def edit(self, note: Note, text: str) -> MutationStatus:
        if not text.strip():
            self.notice.setText("Note text cannot be empty.")
            return MutationStatus.INVALID_INPUT
        result = self.perform(note, lambda: edit_note(self.notes_path, note, text))
        if result is MutationStatus.SUCCESS:
            self.reload()
            visible = self.select_note(note, text.strip())
            self.notice.setText("Note updated." if visible else "Note updated. It no longer matches the current filters.")
        return result

    @Slot()
    def edit_selected(self) -> None:
        note = self.selected_note()
        if note is None:
            return
        if self._edit_dialog is not None:
            self._edit_dialog.raise_()
            return
        self._edit_dialog = EditDialog(self, note)
        self._edit_dialog.finished.connect(self.edit_finished)
        self._edit_dialog.open()
        self._edit_dialog.editor.setFocus()

    @Slot()
    def edit_finished(self) -> None:
        self._edit_dialog = None

    @Slot()
    def mark_selected_done(self) -> None:
        note = self.selected_note()
        if note is None or "todo" not in note.tags or note.is_done:
            return
        result = self.perform(note, lambda: mark_done(self.notes_path, note))
        if result is MutationStatus.SUCCESS:
            self.reload()
            self.select_note(note, note.text.replace("☐", "☑", 1))
            self.notice.setText("Note marked done.")

    @staticmethod
    def delete_preview(note: Note) -> str:
        lines = note.text.splitlines()
        preview = "\n".join(lines[:3])
        return preview[:177].rstrip() + "..." if len(lines) > 3 or len(preview) > 180 else preview

    @Slot()
    def delete_selected(self) -> None:
        note = self.selected_note()
        if note is None:
            return
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Delete note")
        prompt.setTextFormat(Qt.TextFormat.PlainText)
        prompt.setText("Delete this note?\n\n" + self.delete_preview(note))
        prompt.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        prompt.setDefaultButton(QMessageBox.StandardButton.No)
        answer = prompt.exec()
        prompt.deleteLater()
        if answer == QMessageBox.StandardButton.Yes:
            self.delete(note)

    def delete(self, note: Note) -> MutationStatus:
        # Capture the post-delete baseline before writing, so undo never overwrites later edits.
        try:
            lines = self.notes_path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeError):
            self.notice.setText("Could not delete note. Check the file and try again.")
            return MutationStatus.IO_ERROR
        end = note.line_number + 1
        while end < len(lines) and lines[end].startswith("  "):
            end += 1
        removed = lines[note.line_number:end]
        baseline = lines[:note.line_number] + lines[end:]
        result = self.perform(note, lambda: delete_note(self.notes_path, note))
        if result is MutationStatus.SUCCESS:
            self._undo = (note, removed, baseline)
            self.undo_button.setEnabled(True)
            self.reload()
            self.notice.setText("Note deleted. Undo is available for this session.")
        return result

    @Slot()
    def undo_delete(self) -> None:
        if self._undo is None:
            return
        note, removed, baseline = self._undo
        try:
            lines = self.notes_path.read_text(encoding="utf-8").splitlines(keepends=True)
            insert_at = min(note.line_number, len(lines))
            if lines[:len(baseline)] != baseline or (insert_at < len(lines) and lines[insert_at].startswith("  ")):
                self.notice.setText("Notes changed after deletion. Undo cannot safely restore this note.")
                return
            lines[insert_at:insert_at] = removed
            _atomic_write(self.notes_path, "".join(lines))
        except (OSError, UnicodeError):
            self.notice.setText("Could not restore deleted note. Undo is still available.")
            return
        self._undo = None
        self.undo_button.setEnabled(False)
        self.reload()
        self.select_note(note, note.text)
        self.notice.setText("Deletion undone.")

    @Slot()
    def copy_selected(self) -> None:
        note = self.selected_note()
        if note is not None:
            QApplication.clipboard().setText(note.text)
            self.notice.setText("Copied.")

    @Slot(QPoint)
    def context_menu(self, position: QPoint) -> None:
        index = self.view.indexAt(position)
        if not index.isValid():
            return
        self.view.setCurrentIndex(index)
        menu = QMenu(self)
        for action in self.note_actions.values():
            menu.addAction(action)
        menu.exec(self.view.viewport().mapToGlobal(position))
        menu.deleteLater()

    def confirm_discard_edit(self) -> bool:
        dialog = self._edit_dialog
        if dialog is None:
            return True
        if dialog.editor.toPlainText() != dialog.original_text:
            answer = QMessageBox.question(
                dialog, "Unsaved changes", "Discard changes to this note?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                dialog.raise_()
                dialog.activateWindow()
                return False
        dialog.reject()
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if not self.confirm_discard_edit():
            event.ignore()
            return
        if self.managed:
            event.ignore()
            self.close_requested.emit()
        else:
            event.accept()
