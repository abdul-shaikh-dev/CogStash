"""Capture and read-only Browse prototype. No access to the user's default config."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, QPersistentModelIndex, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from cogstash.core import Note, append_note_to_file, parse_notes, search_notes
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
            return f"{note.timestamp:%d %b %Y  %H:%M}\n{note.text}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return note.text
        return None

    def replace(self, notes: list[Note]) -> None:
        self.beginResetModel()
        self.notes = notes
        self.endResetModel()


class CaptureEdit(QPlainTextEdit):
    save_requested = Signal()
    dismiss_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss_requested.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.save_requested.emit()
        else:
            super().keyPressEvent(event)


class CaptureWindow(QWidget):
    saved = Signal()

    def __init__(self, notes_path: Path) -> None:
        super().__init__()
        self.notes_path = notes_path
        self.setWindowTitle("CogStash · Capture prototype")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.resize(520, 230)
        layout = QVBoxLayout(self)
        heading = QLabel("Capture a thought")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        self.editor = CaptureEdit()
        self.editor.setAccessibleName("Note text")
        self.editor.setPlaceholderText("What's on your mind?")
        layout.addWidget(self.editor)
        self.status = QLabel("Enter to save · Shift+Enter for a new line · Esc to dismiss")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.editor.save_requested.connect(self.save_note)
        self.editor.dismiss_requested.connect(self.hide)

    @Slot()
    def reveal(self) -> None:
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
        if not append_note_to_file(text, self.notes_path):
            self.status.setText("Could not save. Your text is retained; check the notes file and try again.")
            return
        self.editor.clear()
        self.status.setText("Saved. Enter to save · Shift+Enter for a new line · Esc to dismiss")
        self.saved.emit()
        self.hide()


class BrowseWindow(QWidget):
    def __init__(self, notes_path: Path) -> None:
        super().__init__()
        self.notes_path = notes_path
        self.notes: list[Note] = []
        self.setWindowTitle("CogStash · Browse prototype")
        self.resize(760, 620)
        layout = QVBoxLayout(self)
        title = QLabel("Your notes")
        title.setObjectName("heading")
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your notes…")
        self.search.setAccessibleName("Search notes")
        layout.addWidget(self.search)
        self.model = NoteModel()
        self.view = QListView()
        self.view.setAccessibleName("Notes")
        self.view.setModel(self.model)
        self.view.setWordWrap(True)
        self.view.setSpacing(6)
        layout.addWidget(self.view)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.action_row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        self.action_row.addWidget(refresh)
        layout.addLayout(self.action_row)
        self.search.textChanged.connect(self.apply_filter)
        self.reload()

    @Slot()
    def reload(self) -> None:
        try:
            self.notes = sorted(parse_notes(self.notes_path), key=lambda n: (n.timestamp, n.index), reverse=True)
        except (OSError, ValueError, UnicodeError) as exc:
            self.notes = []
            self.model.replace([])
            self.status.setText(f"Could not read notes: {exc}")
            return
        self.apply_filter()

    @Slot()
    def apply_filter(self) -> None:
        self.model.replace(search_notes(self.notes, self.search.text()))
        self.status.setText(f"{len(self.model.notes)} of {len(self.notes)} notes · {self.notes_path}")

    def closeEvent(self, event: QCloseEvent) -> None:
        # Closing Browse quits only when there is no tray recovery path.
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            QApplication.quit()


class Runtime(QObject):
    capture_requested = Signal()

    def __init__(self, app: QApplication, notes: Path) -> None:
        super().__init__()
        self.listener: Any = None
        self.capture = CaptureWindow(notes)
        self.browse = BrowseWindow(notes)
        self.capture.saved.connect(self.browse.reload)
        self.capture_requested.connect(self.capture.reveal, Qt.ConnectionType.QueuedConnection)
        capture_button = QPushButton("Capture")
        capture_button.clicked.connect(self.capture.reveal)
        self.browse.action_row.addWidget(capture_button)
        quit_button = QPushButton("Quit")
        quit_button.clicked.connect(app.quit)
        self.browse.action_row.addWidget(quit_button)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.browse.action_row.addWidget(self.warning)
        self.tray = QSystemTrayIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), self)
        self.tray.setToolTip("CogStash Qt prototype")
        self.menu = QMenu()
        for text, callback in (("Capture", self.capture.reveal), ("Browse", self.show_browse), ("Quit", app.quit)):
            action = QAction(text, self.menu)
            action.triggered.connect(callback)
            self.menu.addAction(action)
        self.tray.setContextMenu(self.menu)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        app.aboutToQuit.connect(self.shutdown)

    @Slot()
    def show_browse(self) -> None:
        self.browse.reload()
        self.browse.showNormal()
        self.browse.raise_()
        self.browse.activateWindow()

    def start_hotkey(self, hotkey: str) -> None:
        try:
            from pynput.keyboard import GlobalHotKeys

            listener = GlobalHotKeys({hotkey: self.capture_requested.emit})
            listener.start()
            self.listener = listener
        except Exception as exc:
            self.warning.setText(f"Global hotkey unavailable: {exc}. Use Capture here or in the tray.")

    @Slot()
    def shutdown(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener.join(timeout=1)
            self.listener = None
        self.tray.hide()


def run(notes: Path, hotkey: str, theme: str, enable_hotkey: bool) -> int:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    palette = THEMES[theme]
    app.setStyleSheet(f"""
        QWidget {{ background: {palette['bg']}; color: {palette['fg']}; font-size: 14px; }}
        QLineEdit, QPlainTextEdit, QListView {{ background: {palette['entry_bg']}; border: 1px solid {palette['muted']}; border-radius: 6px; padding: 10px; }}
        QPushButton {{ padding: 8px 18px; border: 1px solid {palette['accent']}; border-radius: 6px; }}
        QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus {{ border: 2px solid {palette['accent']}; }}
        QListView::item {{ padding: 12px; border-bottom: 1px solid {palette['muted']}; }}
        QListView::item:selected {{ background: {palette['accent']}; color: {palette['bg']}; }}
        QLabel#heading {{ font-size: 24px; font-weight: 600; padding: 8px 0; }}
    """)
    runtime = Runtime(app, notes)
    if enable_hotkey:
        runtime.start_hotkey(hotkey)
    runtime.show_browse()
    return app.exec()
