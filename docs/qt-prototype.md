# Qt Widgets prototype

This is the first implementation slice of issue #57. The normal GUI still uses Tkinter. The prototype has capture, a read-only searchable Browse list, tray actions, and a global-hotkey adapter. It does not yet provide settings, tag autocomplete, note editing/deletion, onboarding, or production feature parity.

## Run

The Qt extra requires Python 3.10 or newer. The tested local pair is Python 3.14.0 with PySide6 Essentials 6.11.2 on Windows 11. Existing non-Qt entry points retain their declared Python support.

```powershell
uv sync --extra dev --extra qt
uv run python -m cogstash.ui.qt --notes ./prototype-notes.md
```

The explicit notes path is required to avoid silently writing to personal notes during evaluation. The prototype does not read or write the default config. Use `--no-hotkey` when another CogStash instance is running, or provide a different `--hotkey`. The Browse window opens at startup so errors and fallback Capture/Quit controls remain reachable. Escape hides capture and retains the draft; successful save clears it. Save failures and notes over the core's 10,000-character limit retain the input.

```powershell
uv run python scripts/build_qt.py
./dist/qt-prototype/CogStash-Qt-Prototype/CogStash-Qt-Prototype.exe --notes ./prototype-notes.md
```

This is a console-enabled onedir diagnostic build. Production build targets and installer payloads are unchanged. No release has been published.

## Architecture

- `ui/qt/__main__.py` parses prototype-only options and imports Qt lazily.
- `ui/qt/app.py` owns one QApplication, capture, the list model, Browse, and runtime resources.
- Background hotkey callbacks emit a queued Qt signal. They do not operate on widgets.
- Existing core parsing, saving, and search functions are reused without changes.
- PySide6 Essentials is optional; QtCharts, Qt Graphs, QML, and Qt Quick are excluded from the prototype build.
- The current implementation does not detect all asynchronous pynput listener failures. Cross-platform activation and global shortcut behavior require further validation.

## Validation recorded on 2026-10-02

- Seven prototype behavioral tests plus existing core/CLI tests: 184 passed.
- Full suite: 341 passed. The initial three Tk settings failures came from tests reading the real Windows startup directory. UI tests now isolate APPDATA per test, preserving the application behavior while removing dependence on the host startup state.
- Ruff and mypy pass after the prototype type fixes.
- PyInstaller creates a 117.9 MiB Windows onedir artifact; source and packaged `--help` pass. A clean rebuilt executable also remained running for four seconds under offscreen Qt without a traceback, then the test terminated it.
- Offscreen visual inspection covers capture and filtered Browse with the Tokyo Night theme. The inspection environment required explicitly loading the system font; it does not validate native Windows focus or scaling.
- A synthetic 10,000-note fixture reloaded in about 102 ms and a search update took about 6 ms in an offscreen local run. These are illustrative measurements, not a repeatable benchmark or a Tk comparison.

The first packaged GUI smoke test exposed an incompatible ICU DLL from Poppler on the session PATH. The build script now prioritizes Windows System32 during dependency resolution. A clean rebuild excludes that unrelated ICU copy and starts successfully. No system DLLs were modified.

## Remaining before closing #57

Verify native hotkey-to-input latency and focus from an editor, browser, and terminal; repeated activation; multiple monitors and display scales; idle memory and cold launch against Tk; a Windows machine without Python; other supported desktop platforms; and a module/license inventory with all required distribution notices. The prototype is not evidence that these checks have passed.

Qt Core/Gui/Widgets and PySide6 have open-source licensing options with obligations. Check the actual bundled files before distribution. Do not infer that every module shipped by Qt is LGPL. References: https://doc.qt.io/qt-6/licensing.html and https://www.qt.io/development/open-source-lgpl-obligations.

## Cleanup

The obsolete `docs/superpowers/plans` directory was removed at the user's request. Historical specs remain. Twelve old checkouts and stale worktree registrations were removed while retaining branch references. The `issue-13-code-quality-followups` checkout remains because Windows denies access to its old test directories; no ACL changes were made.
