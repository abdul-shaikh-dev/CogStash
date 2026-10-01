"""Build isolated Qt evaluation artifacts without changing release defaults."""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

from _artifacts import get_executable_name
from qt_notices import write_notices

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_QT = ("PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtCharts", "PySide6.QtGraphs", "PySide6.QtTest")


def build(*, candidate: bool, with_cli: bool, dist: Path, work: Path) -> Path:
    if not (3, 10) <= sys.version_info[:2] < (3, 15):
        raise RuntimeError("The Qt candidate requires Python 3.10 through 3.14.")
    version = importlib.metadata.version("cogstash")
    name = get_executable_name(target="ui", bundle_mode="onedir", version=version) if candidate else "CogStash-Qt-Prototype"
    entry = "candidate.py" if candidate else "__main__.py"
    build_env = os.environ.copy()
    if sys.platform == "win32":
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        build_env["PATH"] = str(system32) + os.pathsep + build_env.get("PATH", "")
    command = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "src/cogstash/ui/qt" / entry),
        "--name", name, "--onedir", "--noconfirm", "--clean",
        "--paths", str(ROOT / "src"), "--copy-metadata", "cogstash",
        "--distpath", str(dist), "--workpath", str(work / "ui"), "--specpath", str(work),
        "--collect-data", "shiboken6",
    ]
    for module in ("tkinter", "pystray", *EXCLUDED_QT):
        command.extend(["--exclude-module", module])
    subprocess.run(command, check=True, env=build_env)
    bundle = dist / name
    notices = write_notices(bundle, ROOT)
    print(f"Diagnostic notices and inventory: {notices}. License review remains incomplete.")
    if with_cli:
        cli_name = get_executable_name(target="cli", bundle_mode="onefile", version=version)
        command = [
            sys.executable, "-m", "PyInstaller", str(ROOT / "src/cogstash/cli/__main__.py"),
            "--name", cli_name, "--onefile", "--noconfirm", "--clean",
            "--paths", str(ROOT / "src"), "--copy-metadata", "cogstash",
            "--distpath", str(dist), "--workpath", str(work / "cli"), "--specpath", str(work),
        ]
        for module in ("PySide6", "shiboken6", "tkinter", "pystray", "pynput", "PIL", "cogstash.ui"):
            command.extend(["--exclude-module", module])
        subprocess.run(command, check=True, env=build_env)
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="store_true", help="Use installed launch defaults and installer-compatible artifact names")
    parser.add_argument("--with-cli", action="store_true", help="Also build an independent CLI executable")
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--build-dir", type=Path)
    args = parser.parse_args()
    profile = "qt-candidate" if args.candidate else "qt-prototype"
    build(candidate=args.candidate, with_cli=args.with_cli,
          dist=(args.dist_dir or ROOT / "dist" / profile).resolve(),
          work=(args.build_dir or ROOT / "build" / profile).resolve())


if __name__ == "__main__":
    main()
