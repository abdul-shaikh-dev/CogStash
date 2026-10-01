"""Qt application ownership and GUI-thread command dispatch."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QMessageBox, QPushButton, QStyle, QSystemTrayIcon

from cogstash.core import CogStashConfig, merge_tags
from cogstash.ui.qt.app import BrowseWindow, CaptureWindow, apply_theme
from cogstash.ui.qt.hotkeys import HotkeyAdapter
from cogstash.ui.qt.settings import SettingsDialog, WelcomeDialog, onboarding_kind
from cogstash.ui.ui_shared import THEMES, WINDOW_SIZES


class Runtime(QObject):
    capture_requested = Signal()

    def __init__(self, app: QApplication, notes: Path, window_size: str = "default", theme: str = "tokyo-night") -> None:
        super().__init__()
        self.app = app
        self.notes = notes
        self.window_size = window_size
        self.theme = theme
        self.config = CogStashConfig(output_file=notes, window_size=window_size, theme=theme)
        self.config_path: Path | None = None
        self._settings: SettingsDialog | None = None
        self._welcome: WelcomeDialog | None = None
        self.closed = False
        self._capture: CaptureWindow | None = None
        self._browse: BrowseWindow | None = None
        self.warning_text = ""
        self.warning: QLabel | None = None
        self.hotkeys = HotkeyAdapter(self)
        self.hotkeys.activated.connect(self.show_capture, Qt.ConnectionType.QueuedConnection)
        self.hotkeys.failed.connect(self.show_warning, Qt.ConnectionType.QueuedConnection)
        self.capture_requested.connect(self.show_capture, Qt.ConnectionType.QueuedConnection)
        self.tray = QSystemTrayIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), self)
        self.tray.setToolTip("CogStash Qt prototype")
        self.menu = QMenu()
        for text, callback in (
            ("Capture", self.show_capture), ("Open notes file", self.open_notes),
            ("Browse Notes", self.show_browse),
        ):
            action = QAction(text, self.menu)
            action.triggered.connect(callback)
            self.menu.addAction(action)
        self.menu.addAction("Settings", self.show_settings)
        self.menu.addSeparator()
        self.menu.addAction("Quit", self.request_quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        # Qt can add the icon if the tray becomes available later.
        self.tray.show()
        app.aboutToQuit.connect(self.shutdown)

    @property
    def capture(self) -> CaptureWindow:
        if self._capture is None:
            self._capture = CaptureWindow(self.notes, window_size=self.window_size)
            self._capture.editor.tags = merge_tags(self.config)[0]
            self._capture.saved.connect(self.note_saved)
        return self._capture

    @property
    def browse(self) -> BrowseWindow:
        if self._browse is None:
            self._browse = BrowseWindow(self.notes, managed=True, theme=self.theme,
                                        configured_tags=merge_tags(self.config)[0])
            self._browse.close_requested.connect(self.close_browse)
            for text, callback in (("Capture", self.show_capture), ("Settings", self.show_settings), ("Quit", self.request_quit)):
                button = QPushButton(text)
                button.clicked.connect(callback)
                self._browse.action_row.addWidget(button)
            self.warning = QLabel(self.warning_text)
            self.warning.setWordWrap(True)
            layout = self._browse.layout()
            assert layout is not None
            layout.addWidget(self.warning)
        return self._browse

    def configure(self, config: CogStashConfig, config_path: Path | None) -> None:
        self.config_path = config_path
        self.apply_config(config)

    def can_apply_config(self, config: CogStashConfig) -> str | None:
        if config.output_file != self.notes:
            if self._capture is not None and self._capture.editor.toPlainText().strip():
                return "Save or clear the capture draft before changing the notes file."
            if self._browse is not None and self._browse._edit_dialog is not None:
                return "Finish or cancel the note edit before changing the notes file."
        return None

    def apply_config(self, config: CogStashConfig) -> None:
        changed_path = self.notes != config.output_file
        changed_hotkey = self.config.hotkey != config.hotkey
        self.config = config
        assert config.output_file is not None
        self.notes = config.output_file
        self.window_size = config.window_size
        self.theme = config.theme
        apply_theme(self.app, self.theme)
        if self._capture is not None:
            self._capture.notes_path = self.notes
            self._capture.size_preset = WINDOW_SIZES[self.window_size]
            self._capture.setFixedWidth(self._capture.size_preset["width"])
            self._capture.editor.tags = merge_tags(config)[0]
            self._capture.editor.update_suggestions()
            self._capture.grow_editor()
        if self._browse is not None:
            self._browse.notes_path = self.notes
            self._browse.configured_tags = merge_tags(config)[0]
            self._browse.delegate.colors = THEMES[self.theme]
            if changed_path:
                self._browse._undo = None
                self._browse.undo_button.setEnabled(False)
            self._browse.reload()
        if changed_hotkey and self._settings is not None:
            self.show_warning("Settings saved. Restart CogStash to use the changed global hotkey.")

    @Slot()
    def show_settings(self, setup: bool = False) -> None:
        if self.closed:
            return
        if self._settings is None:
            try:
                self._settings = SettingsDialog(self.config, self.config_path, self.apply_config,
                                                setup=setup, can_apply=self.can_apply_config)
            except (OSError, ValueError) as exc:
                self.show_warning(f"Could not open settings: {exc}")
                return
            self._settings.finished.connect(self.settings_finished)
        self._settings.showNormal()
        self._settings.raise_()
        self._settings.activateWindow()

    def settings_finished(self) -> None:
        if self._settings is not None:
            self._settings.deleteLater()
            self._settings = None

    def show_onboarding(self) -> None:
        if self.config_path is None:
            return
        kind = onboarding_kind(self.config)
        if kind == "setup":
            self.show_settings(setup=True)
        elif kind is not None:
            try:
                self._welcome = WelcomeDialog(self.config, self.config_path, kind, self.apply_config)
                self._welcome.show()
            except (OSError, ValueError) as exc:
                self.show_warning(f"Could not open welcome: {exc}")

    @Slot()
    def show_capture(self) -> None:
        if not self.closed:
            self.capture.reveal()

    @Slot()
    def show_browse(self) -> None:
        if self.closed:
            return
        if self._browse is not None:
            self._browse.reload()
        browse = self.browse
        browse.showNormal()
        browse.raise_()
        browse.activateWindow()

    @Slot()
    def note_saved(self) -> None:
        if not self.closed and self._browse is not None:
            self._browse.reload()

    @Slot(str)
    def show_warning(self, message: str) -> None:
        if self.closed:
            return
        self.warning_text = message
        self.show_browse()
        if self.warning is not None:
            self.warning.setText(message)

    def start_hotkey(self, hotkey: str) -> None:
        if not self.closed:
            self.config.hotkey = hotkey
            self.hotkeys.start(hotkey)

    @Slot(QSystemTrayIcon.ActivationReason)
    def tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_capture()

    @Slot()
    def open_notes(self) -> None:
        if self.closed:
            return
        if not self.notes.is_file():
            self.show_warning("Save a note first to create the notes file.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.notes.resolve()))):
            self.show_warning("Could not open the notes file. Check the file association for Markdown files.")

    @Slot()
    def close_browse(self) -> None:
        if self.closed:
            return
        if self.tray.isVisible() and QSystemTrayIcon.isSystemTrayAvailable():
            self.browse.hide()
        else:
            self.request_quit()

    @Slot()
    def request_quit(self) -> None:
        if self.closed:
            return
        if self._settings is not None and self._settings.has_changes():
            answer = QMessageBox.question(
                self._settings, "Unsaved settings", "Quit and discard the unsaved settings?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                self.show_settings()
                return
        if self._browse is not None and not self._browse.confirm_discard_edit():
            return
        if self._capture is not None and self._capture.editor.toPlainText().strip():
            answer = QMessageBox.question(
                self._capture, "Unsaved note", "Quit and discard the unsaved note?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                self.show_capture()
                return
        self.shutdown()
        self.app.quit()

    @Slot()
    def shutdown(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.hotkeys.shutdown()
        self.tray.hide()
        self.menu.close()
        if self._capture is not None:
            self._capture.hide()
        if self._browse is not None:
            self._browse.hide()
        if self._settings is not None:
            self._settings.reject()
        if self._welcome is not None:
            self._welcome.reject()
