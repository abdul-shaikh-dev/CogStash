"""Draft-based settings for the optional Qt application."""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cogstash import __version__
from cogstash.core import DEFAULT_SMART_TAGS, CogStashConfig
from cogstash.core.config import load_config, save_config, write_json_file
from cogstash.ui import install_state
from cogstash.ui.qt.startup import StartupManager
from cogstash.ui.ui_shared import THEMES, WINDOW_SIZES


def read_config(path: Path) -> CogStashConfig:
    """Avoid creating defaults or overwriting malformed files during setup."""
    if not path.exists():
        return CogStashConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must contain a JSON object.")
    # Validate container/value types that the legacy loader assumes are strings.
    for key in ("theme", "window_size", "hotkey", "output_file", "log_file"):
        if key in data and not isinstance(data[key], str):
            raise ValueError(f"Configuration field '{key}' must be text.")
    if "launch_at_startup" in data and not isinstance(data["launch_at_startup"], bool):
        raise ValueError("Configuration field 'launch_at_startup' must be true or false.")
    tags = data.get("tags")
    if tags is not None:
        if not isinstance(tags, dict):
            raise ValueError("Configuration tags must be an object.")
        for name, props in tags.items():
            if not isinstance(props, dict) or not all(isinstance(props.get(k), str) for k in ("emoji", "color")):
                raise ValueError(f"Tag '{name}' needs text emoji and color fields.")
            if not props["emoji"].strip() or not re.fullmatch(r"#[0-9a-fA-F]{6}", props["color"]):
                raise ValueError(f"Tag '{name}' needs an emoji and a #RRGGBB color.")
    return load_config(path)


def snapshot(path: Path | None) -> bytes | None:
    return path.read_bytes() if path is not None and path.exists() else None


def persist(config: CogStashConfig, path: Path, baseline: bytes | None) -> None:
    """Stage through the core serializer, preserve extra keys, then replace atomically."""
    if snapshot(path) != baseline:
        raise ValueError("Configuration changed elsewhere. Restart CogStash to load the external changes before saving.")
    previous = json.loads(baseline) if baseline is not None else {}
    if not isinstance(previous, dict):
        raise ValueError("Configuration must contain a JSON object.")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    staged = Path(name)
    try:
        save_config(config, staged)
        # save_config logs write failures; an empty/unreadable staging file is a failure.
        try:
            data = json.loads(staged.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OSError(f"Could not write configuration at {path}. Check file permissions and free disk space.") from exc
        previous.pop("tags", None)
        write_json_file(staged, {**previous, **data})
        if snapshot(path) != baseline:
            raise ValueError("Configuration changed elsewhere. Restart CogStash to load the external changes before saving.")
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def onboarding_kind(config: CogStashConfig) -> str | None:
    if not config.last_seen_version:
        return "setup"
    if install_state.should_show_installer_welcome(config, __version__):
        return "installed"
    return "updated" if config.last_seen_version != __version__ else None


def validate_hotkey(value: str) -> None:
    if not value.strip():
        raise ValueError("Hotkey is required.")
    try:
        from pynput.keyboard import HotKey
        HotKey.parse(value.strip())
    except ImportError as exc:
        raise ValueError("Hotkey validation needs a supported desktop session. Keep the existing hotkey or try again in a desktop session.") from exc
    except Exception as exc:
        raise ValueError("Enter a hotkey such as <ctrl>+<shift>+<space> or <ctrl>+<alt>+h.") from exc


class SettingsDialog(QDialog):
    def __init__(
        self, config: CogStashConfig, config_path: Path | None,
        on_saved: Callable[[CogStashConfig], None], parent: QWidget | None = None,
        *, setup: bool = False, can_apply: Callable[[CogStashConfig], str | None] | None = None,
        startup: StartupManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.original = copy.deepcopy(config)
        self.config_path = config_path
        self.baseline = snapshot(config_path)
        self.on_saved = on_saved
        self.can_apply = can_apply
        self.setup = setup
        self.startup_manager = startup
        self.startup_baseline = startup.snapshot() if startup is not None else None
        self.setWindowTitle("Welcome to CogStash" if setup else "CogStash Settings")
        self.resize(640, 590)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Choose a notes file and shortcut. Capture with the shortcut, press Enter to save, or Shift+Enter for a new line. Browse lets you search, edit, and finish todos."
            if setup else "Changes apply when you save. A changed global hotkey takes effect after restarting CogStash."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        general = QWidget()
        form = QFormLayout(general)
        self.notes = QLineEdit(str(config.output_file))
        self.notes.setAccessibleName("Notes file")
        row = QHBoxLayout()
        row.addWidget(self.notes)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_file)
        row.addWidget(browse)
        label = QLabel("&Notes file")
        label.setBuddy(self.notes)
        form.addRow(label, row)
        self.hotkey = QLineEdit(config.hotkey)
        self.hotkey.setAccessibleName("Global hotkey")
        form.addRow("&Hotkey", self.hotkey)
        test = QPushButton("Check hotkey syntax")
        test.clicked.connect(self.test_hotkey)
        form.addRow(test)
        self.startup = QCheckBox("Launch CogStash at system startup")
        self.startup.setChecked(install_state.startup_script_exists() if os.name == "nt" else config.launch_at_startup)
        if startup is not None:
            self.startup.setChecked(self.startup_baseline is not None)
        self.startup.setEnabled(startup is not None)
        form.addRow(self.startup)
        startup_help = QLabel("Startup is read-only in the Qt prototype. Windows shows the existing CogStash startup script. Startup integration will be enabled with the installed Qt build." if os.name == "nt" else "Startup management is supported on Windows only.")
        if startup is not None:
            startup_help.setText("Start this CogStash build with this configuration when you sign in. Changes apply on Save.")
        startup_help.setWordWrap(True)
        form.addRow(startup_help)
        self.tabs.addTab(general, "&General")
        appearance = QWidget()
        appearance_form = QFormLayout(appearance)
        self.theme = QComboBox()
        self.theme.addItems(list(THEMES))
        self.theme.setCurrentText(config.theme)
        self.theme.setAccessibleName("Theme")
        appearance_form.addRow("&Theme", self.theme)
        self.window_size = QComboBox()
        self.window_size.addItems(list(WINDOW_SIZES))
        self.window_size.setCurrentText(config.window_size)
        self.window_size.setAccessibleName("Capture window size")
        appearance_form.addRow("Window &size", self.window_size)
        self.tabs.addTab(appearance, "&Appearance")
        tags_page = QWidget()
        tags_layout = QVBoxLayout(tags_page)
        builtins = QLabel("Built-in tags: " + ", ".join("#" + name for name in DEFAULT_SMART_TAGS))
        builtins.setWordWrap(True)
        tags_layout.addWidget(builtins)
        self.tags = QTableWidget(0, 3)
        self.tags.setHorizontalHeaderLabels(["Name", "Emoji", "Color (#RRGGBB)"])
        self.tags.setAccessibleName("Custom tags")
        self.tags.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for name, props in (config.tags or {}).items():
            self.add_tag(name, props["emoji"], props["color"])
        tags_layout.addWidget(self.tags)
        tag_buttons = QHBoxLayout()
        add = QPushButton("Add tag")
        add.clicked.connect(lambda: self.add_tag())
        remove = QPushButton("Remove selected tag")
        remove.clicked.connect(lambda: self.tags.removeRow(self.tags.currentRow()) if self.tags.currentRow() >= 0 else None)
        tag_buttons.addWidget(add)
        tag_buttons.addWidget(remove)
        tags_layout.addLayout(tag_buttons)
        self.tabs.addTab(tags_page, "&Tags")
        storage = QLabel(f"Config: {config_path}" if config_path else "Session only. Launch with --config PATH to save settings between runs.")
        storage.setTextFormat(Qt.TextFormat.PlainText)
        storage.setWordWrap(True)
        layout.addWidget(storage)
        self.error = QLabel()
        self.error.setAccessibleName("Settings status")
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.notes.setFocus()
        self.initial_fields = self.fields()

    def fields(self) -> tuple[object, ...]:
        cells = [self.tags.item(row, column) for row in range(self.tags.rowCount()) for column in range(3)]
        return (self.notes.text(), self.hotkey.text(), self.theme.currentText(), self.window_size.currentText(),
                tuple(item.text() if item is not None else "" for item in cells), self.startup.isChecked())

    def has_changes(self) -> bool:
        return self.fields() != self.initial_fields

    def add_tag(self, name: str = "", emoji: str = "", color: str = "#ffffff") -> None:
        row = self.tags.rowCount()
        self.tags.insertRow(row)
        for column, value in enumerate((name, emoji, color)):
            self.tags.setItem(row, column, QTableWidgetItem(value))
        self.tags.setCurrentCell(row, 0)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Choose notes file", self.notes.text(), "Markdown (*.md);;Text (*.txt);;All files (*)")
        if path:
            self.notes.setText(path)

    def test_hotkey(self) -> None:
        try:
            validate_hotkey(self.hotkey.text())
        except ValueError as exc:
            self.error.setText(str(exc))
        else:
            self.error.setText("Syntax is valid. This does not test OS permissions or shortcut conflicts. Save and restart to use a changed hotkey.")

    def candidate(self) -> CogStashConfig:
        raw_path = self.notes.text().strip()
        if not raw_path:
            raise ValueError("Notes file path is required.")
        if "\x00" in raw_path:
            raise ValueError("Notes file path contains an invalid character.")
        path = Path(raw_path).expanduser()
        if path.is_dir():
            raise ValueError("Notes file path must point to a file, not a directory.")
        if self.config_path is not None and path.resolve() == self.config_path.resolve():
            raise ValueError("Notes and configuration must use different files.")
        for parent in path.parents:
            if parent.exists() and not parent.is_dir():
                raise ValueError("A parent of the notes file is a file, not a directory.")
        hotkey = self.hotkey.text().strip()
        if not hotkey or hotkey != self.original.hotkey:
            validate_hotkey(hotkey)
        tags: dict[str, dict[str, str]] = {}
        for row in range(self.tags.rowCount()):
            items = [self.tags.item(row, column) for column in range(3)]
            name, emoji, color = [item.text().strip() if item is not None else "" for item in items]
            name = name.lower()
            if not re.fullmatch(r"\w+", name) or not emoji or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError(f"Tag row {row + 1}: use a name with letters, digits or underscores, an emoji, and a #RRGGBB color.")
            if name in tags:
                raise ValueError(f"Duplicate custom tag: #{name}.")
            tags[name] = {"emoji": emoji, "color": color}
        result = replace(self.original, output_file=path, hotkey=hotkey, theme=self.theme.currentText(), window_size=self.window_size.currentText(), tags=tags or None)
        if self.startup_manager is not None:
            result.launch_at_startup = self.startup.isChecked()
        if self.setup:
            result.last_seen_version = __version__
            if install_state.is_installed_windows_run():
                result.last_seen_installer_version = __version__
        return result

    def save(self) -> None:
        try:
            candidate = self.candidate()
            if self.can_apply is not None:
                reason = self.can_apply(candidate)
                if reason:
                    raise ValueError(reason)
            transaction = self.startup_manager.change(candidate.launch_at_startup, self.startup_baseline) if self.startup_manager is not None else nullcontext()
            with transaction:
                if self.config_path is not None:
                    persist(candidate, self.config_path, self.baseline)
        except (OSError, ValueError) as exc:
            self.error.setText(f"Could not save settings: {exc}")
            return
        self.on_saved(candidate)
        self.accept()


class WelcomeDialog(QDialog):
    def __init__(self, config: CogStashConfig, config_path: Path, kind: str, on_saved: Callable[[CogStashConfig], None]) -> None:
        super().__init__()
        self.setWindowTitle("CogStash updated")
        self.resize(480, 240)
        layout = QVBoxLayout(self)
        message = QLabel(f"Welcome to CogStash {__version__}.\n\n" + (
            "Your existing settings are retained. Windows startup reflects the installer selection. CLI access depends on the PATH option selected during installation."
            if kind == "installed" else "Your existing settings are retained. Open Settings from Browse or the tray to review them."
        ))
        message.setWordWrap(True)
        layout.addWidget(message)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.error)
        baseline = snapshot(config_path)
        button = QPushButton("Got it")
        def acknowledge() -> None:
            candidate = replace(config, last_seen_version=__version__)
            if kind == "installed":
                candidate.last_seen_installer_version = __version__
            try:
                persist(candidate, config_path, baseline)
            except (OSError, ValueError) as exc:
                self.error.setText(f"Could not save: {exc}")
                return
            on_saved(candidate)
            self.accept()
        button.clicked.connect(acknowledge)
        layout.addWidget(button)
