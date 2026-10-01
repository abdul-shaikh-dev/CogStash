"""Compare current Tk/Qt Browse in fresh processes with isolated synthetic notes.

Windows only. Opens short-lived windows; never loads user config or hotkeys.
This measures source Browse construction and idle memory, not full app cold start.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path


def memory_mib() -> dict[str, float]:
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage", "PrivateUsage",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"working_set_mib": counters.WorkingSetSize / 2**20, "private_mib": counters.PrivateUsage / 2**20}


def child(toolkit: str, notes: Path) -> None:
    if toolkit == "qt":
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from cogstash.ui.qt.app import BrowseWindow

        app = QApplication([])
        window = BrowseWindow(notes)
        window.show()
        app.processEvents()
        ready = time.perf_counter()

        def finish() -> None:
            print(json.dumps({"ready": ready, **memory_mib()}), flush=True)
            app.quit()

        QTimer.singleShot(2000, finish)
        app.exec()
    else:
        import tkinter as tk

        from cogstash.core import CogStashConfig
        from cogstash.ui.browse import BrowseWindow

        root = tk.Tk()
        root.withdraw()
        window = BrowseWindow(root, CogStashConfig(output_file=notes, log_file=notes.with_suffix(".log")))
        root.update()
        ready = time.perf_counter()

        def finish() -> None:
            print(json.dumps({"ready": ready, **memory_mib()}), flush=True)
            root.destroy()

        root.after(2000, finish)
        root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", choices=["tk", "qt"], help=argparse.SUPPRESS)
    parser.add_argument("--notes", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, default=Path("build/qt-prototype/browse-benchmark.json"))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This probe uses Windows memory counters.")
    if args.child:
        child(args.child, args.notes)
        return
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    results = []
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    with tempfile.TemporaryDirectory(prefix="cogstash-browse-benchmark-") as directory:
        notes = Path(directory) / "notes.md"
        for count in (0, 1000):
            notes.write_text("".join(
                f"- [2026-10-02 10:00] Synthetic note {i} about a project #idea\n" for i in range(count)
            ), encoding="utf-8")
            for repeat in range(args.repeats):
                for toolkit in (("tk", "qt") if repeat % 2 == 0 else ("qt", "tk")):
                    start = time.perf_counter()
                    run = subprocess.run(
                        [sys.executable, str(Path(__file__).resolve()), "--child", toolkit, "--notes", str(notes)],
                        capture_output=True, text=True, check=True, timeout=60, env=env,
                    )
                    result = json.loads(run.stdout)
                    result["startup_ms"] = (result.pop("ready") - start) * 1000
                    result.update(toolkit=toolkit, notes=count, repeat=repeat + 1)
                    results.append(result)
                    print(json.dumps(result), flush=True)
    summary = []
    for count in (0, 1000):
        for toolkit in ("tk", "qt"):
            group = [r for r in results if r["notes"] == count and r["toolkit"] == toolkit]
            summary.append({"toolkit": toolkit, "notes": count, **{
                key: statistics.median(r[key] for r in group)
                for key in ("startup_ms", "working_set_mib", "private_mib")
            }})
    report = {"platform": platform.platform(), "python": sys.version, "runs": results, "medians": summary}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
