"""Smoke-test candidate UI/CLI artifacts using isolated user data."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _artifacts import get_executable_name
from PyInstaller.archive.readers import CArchiveReader


def archive_modules(executable: Path) -> set[str]:
    archive = CArchiveReader(str(executable))
    names = set(archive.toc)
    for name in archive.toc:
        if name.endswith(".pyz"):
            names.update(archive.open_embedded_archive(name).toc)
    return names


def assert_excluded(names: set[str], prefixes: tuple[str, ...]) -> None:
    offending = sorted(name for name in names if any(name == prefix or name.startswith((prefix + ".", prefix + "/", prefix + "\\")) for prefix in prefixes))
    if offending:
        raise AssertionError(f"Unexpected bundled modules: {offending}")


def check_command(command: list[str], expected: str, env: dict[str, str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=env)
    output = result.stdout + result.stderr
    if result.returncode or "Traceback" in output or expected not in output:
        raise AssertionError(f"Command failed {command}: {result.returncode}\n{output}")


def check_startup(executable: Path, config: Path, notes: Path, env: dict[str, str]) -> None:
    before = config.read_bytes() if config.exists() else None
    original_notes = notes.read_bytes()
    process = subprocess.Popen([str(executable), "--config", str(config), "--notes", str(notes), "--no-hotkey"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    try:
        try:
            output, _ = process.communicate(timeout=4)
            raise AssertionError(f"UI exited early ({process.returncode}): {output}")
        except subprocess.TimeoutExpired:
            process.terminate()
            output, _ = process.communicate(timeout=10)
        if "Traceback" in output:
            raise AssertionError(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
    assert notes.read_bytes() == original_notes, "Startup modified the notes fixture"
    assert (config.read_bytes() if config.exists() else None) == before, "Startup modified the config fixture"


def smoke(dist: Path, version: str) -> dict[str, object]:
    suffix = ".exe" if sys.platform == "win32" else ""
    ui_name = get_executable_name(target="ui", bundle_mode="onedir", version=version)
    cli_name = get_executable_name(target="cli", bundle_mode="onefile", version=version)
    bundle = dist / ui_name
    ui, cli = bundle / (ui_name + suffix), dist / (cli_name + suffix)
    cli_modules = archive_modules(cli)
    assert_excluded(cli_modules, ("PySide6", "shiboken6", "tkinter", "pystray", "pynput", "PIL", "cogstash.ui"))
    ui_modules = archive_modules(ui)
    assert_excluded(ui_modules, ("tkinter", "pystray", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtCharts", "PySide6.QtGraphs"))
    assert any(path.name.startswith("QtWidgets.") for path in bundle.rglob("*")), "QtWidgets extension missing"
    with tempfile.TemporaryDirectory(prefix="cogstash-candidate-smoke-") as directory:
        root = Path(directory)
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "HOME": str(root), "USERPROFILE": str(root), "APPDATA": str(root / "appdata"), "PYTHONIOENCODING": "utf-8"}
        notes = root / "notes.md"
        notes.write_text("- [2026-01-01 12:00] Fixture #idea\n", encoding="utf-8")
        check_command([str(ui), "--help"], "--config", env)
        check_command([str(cli), "--help"], "usage:", env)
        check_command([str(cli), "--version"], version, env)
        check_startup(ui, root / "new.json", notes, env)
        config = root / "existing.json"
        config.write_text(json.dumps({"output_file": str(notes), "last_seen_version": "old", "theme": "light"}), encoding="utf-8")
        check_startup(ui, config, notes, env)
    report = {
        "platform": sys.platform, "python": sys.version.split()[0], "version": version,
        "ui_bytes": sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file()),
        "cli_bytes": cli.stat().st_size, "ui_archive_entries": len(ui_modules), "cli_archive_entries": len(cli_modules),
        "checks": ["help", "CLI version", "first-run startup", "existing-config startup", "fixture preservation", "module exclusions"],
        "interactive_desktop_verified": False,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=Path("dist/qt-candidate"))
    parser.add_argument("--version", default=importlib.metadata.version("cogstash"))
    parser.add_argument("--report", type=Path, default=Path("build/qt-candidate/smoke.json"))
    args = parser.parse_args()
    report = smoke(args.dist_dir.resolve(), args.version)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
