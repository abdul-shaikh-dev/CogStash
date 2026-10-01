"""Capture widgets and theme setup. No access to the user's default config."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCursor, QHideEvent, QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from cogstash.core import DEFAULT_SMART_TAGS, CogStashConfig, append_note_to_file
from cogstash.ui.qt.browse import BrowseWindow as BrowseWindow
from cogstash.ui.ui_shared import THEMES, WINDOW_SIZES


class CaptureEdit(QPlainTextEdit):
    save_requested = Signal()
    dismiss_requested = Signal()

    def __init__(self, tags: dict[str, str] | None = None) -> None:
        super().__init__()
        self.tags = dict(DEFAULT_SMART_TAGS if tags is None else tags)
        self.suggestions = QListWidget()
        self.suggestions.setAccessibleName("Tag suggestions")
        self.suggestions.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.suggestions.hide()
        self.suggestions.itemClicked.connect(self.confirm_tag)
        self.textChanged.connect(self.update_suggestions)
        self.cursorPositionChanged.connect(self.update_suggestions)

    def fragment(self) -> tuple[int, str] | None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return None
        before = QTextCursor(cursor)
        before.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
        match = re.search(r"(?:^|[ \t])#([^\s#]*)$", before.selectedText())
        if match is None:
            return None
        fragment = match.group(1)
        # QTextCursor positions count UTF-16 code units, unlike Python string indexes.
        start = cursor.position() - len(("#" + fragment).encode("utf-16-le")) // 2
        return start, fragment.lower()

    @Slot()
    def update_suggestions(self) -> None:
        fragment = self.fragment()
        matches = [] if fragment is None else [name for name in self.tags if name.startswith(fragment[1])]
        self.suggestions.clear()
        if not matches or (len(matches) == 1 and fragment is not None and matches[0] == fragment[1]):
            self.suggestions.hide()
            return
        for name in matches:
            self.suggestions.addItem(f"{self.tags[name]} #{name}")
            self.suggestions.item(self.suggestions.count() - 1).setData(Qt.ItemDataRole.UserRole, name)
        self.suggestions.setCurrentRow(0)
        row_height = max(self.suggestions.sizeHintForRow(0), self.fontMetrics().height() + 8)
        self.suggestions.setFixedHeight(min(len(matches), 5) * row_height + 24)
        self.suggestions.show()

    def confirm_tag(self) -> None:
        item = self.suggestions.currentItem()
        fragment = self.fragment()
        if item is None or fragment is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        cursor = self.textCursor()
        cursor.setPosition(fragment[0], QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(f"#{name}")
        self.setTextCursor(cursor)
        self.suggestions.hide()
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if self.suggestions.isVisible():
            if key == Qt.Key.Key_Escape:
                self.suggestions.hide()
                return
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                step = -1 if key == Qt.Key.Key_Up else 1
                self.suggestions.setCurrentRow(max(0, min(self.suggestions.count() - 1, self.suggestions.currentRow() + step)))
                return
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter) and not shift:
                self.confirm_tag()
                return
        if key == Qt.Key.Key_Escape:
            self.dismiss_requested.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not shift:
            self.save_requested.emit()
        else:
            super().keyPressEvent(event)


class CaptureWindow(QWidget):
    saved = Signal()

    def __init__(self, notes_path: Path, window_size: str = "default") -> None:
        super().__init__()
        self.notes_path = notes_path
        self.size_preset = WINDOW_SIZES[window_size]
        self.setWindowTitle("CogStash · Capture prototype")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedWidth(self.size_preset["width"])
        layout = QVBoxLayout(self)
        heading = QLabel("Capture a thought")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        self.editor = CaptureEdit()
        self.editor.setAccessibleName("Note text")
        self.editor.setPlaceholderText("What's on your mind?")
        layout.addWidget(self.editor)
        layout.addWidget(self.editor.suggestions)
        self.editor.textChanged.connect(self.grow_editor)
        self.grow_editor()
        self.status = QLabel("Enter to save · Shift+Enter for a new line · Esc to dismiss")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.editor.save_requested.connect(self.save_note)
        self.editor.dismiss_requested.connect(self.hide)

    @Slot()
    def grow_editor(self) -> None:
        lines = min(max(self.editor.blockCount(), self.size_preset["lines"]), self.size_preset["max_lines"])
        self.editor.setFixedHeight(lines * self.editor.fontMetrics().lineSpacing() + 28)
        self.adjustSize()

    def hideEvent(self, event: QHideEvent) -> None:
        self.editor.suggestions.hide()
        super().hideEvent(event)

    @Slot()
    def reveal(self) -> None:
        if not self.isVisible():
            screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.editor.setFocus()

    @Slot()
    def save_note(self) -> None:
        text = self.editor.toPlainText()
        if not text.strip():
            self.status.setText("Write a note before saving.")
            return
        # The core currently truncates long notes. Do not silently lose prototype input.
        if len(text.strip()) > 10_000:
            self.status.setText("This note exceeds 10,000 characters. Shorten it before saving.")
            return
        if not append_note_to_file(text, self.notes_path, self.editor.tags):
            self.status.setText("Could not save. Your text is retained; check the notes file and try again.")
            return
        self.editor.clear()
        self.status.setText("Saved. Enter to save · Shift+Enter for a new line · Esc to dismiss")
        self.saved.emit()
        self.hide()


def apply_theme(app: QApplication, theme: str) -> None:
    palette = THEMES[theme]
    app.setStyleSheet(f"""
        QWidget {{ background: {palette['bg']}; color: {palette['fg']}; font-size: 14px; }}
        QLineEdit, QPlainTextEdit, QListView, QComboBox {{ background: {palette['entry_bg']}; border: 1px solid {palette['muted']}; border-radius: 6px; padding: 10px; }}
        QPushButton {{ padding: 8px 18px; border: 1px solid {palette['accent']}; border-radius: 6px; }}
        QCheckBox:disabled {{ color: {palette['muted']}; }}
        QPushButton:disabled {{ color: {palette['muted']}; border-color: {palette['muted']}; }}
        QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus {{ border: 2px solid {palette['accent']}; }}
        QListView::item {{ padding: 12px; border-bottom: 1px solid {palette['muted']}; }}
        QListView::item:selected {{ background: {palette['accent']}; color: {palette['bg']}; }}
        QLabel#heading {{ font-size: 24px; font-weight: 600; padding: 8px 0; }}
    """)


def run(notes: Path, hotkey: str, theme: str, enable_hotkey: bool, window_size: str = "default",
        config: CogStashConfig | None = None, config_path: Path | None = None) -> int:
    from cogstash.ui.qt.runtime import Runtime

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app, theme)
    runtime = Runtime(app, notes, window_size, theme)
    try:
        if config is not None:
            runtime.configure(config, config_path)
        if enable_hotkey:
            runtime.start_hotkey(hotkey)
        runtime.show_browse()
        if config_path is not None:
            runtime.show_onboarding()
        return app.exec()
    finally:
        runtime.shutdown()
