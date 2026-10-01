"""Build the experimental Qt UI without changing production artifact contracts."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    build_env = os.environ.copy()
    if sys.platform == "win32":
        # Resolve Windows ICU before unrelated SDKs/tools exposing an incompatible icuuc.dll.
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        build_env["PATH"] = str(system32) + os.pathsep + build_env.get("PATH", "")
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        str(root / "src/cogstash/ui/qt/__main__.py"),
        "--name", "CogStash-Qt-Prototype", "--onedir", "--noconfirm", "--clean",
        "--paths", str(root / "src"),
        "--distpath", str(root / "dist/qt-prototype"),
        "--workpath", str(root / "build/qt-prototype"),
        "--specpath", str(root / "build"),
        "--exclude-module", "tkinter", "--exclude-module", "pystray",
        "--exclude-module", "PySide6.QtQml", "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtCharts", "--exclude-module", "PySide6.QtGraphs",
        "--collect-data", "shiboken6",
    ], check=True, env=build_env)


if __name__ == "__main__":
    main()
