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

## Additional Windows validation on 2026-10-02

The user verified the packaged capture flow from Notepad with Ctrl+Alt+Shift+J: the capture window received typing without an extra click, Enter saved, and capture hid. The isolated test notes file confirmed the saved entries. This is a manual functional check, not a measured hotkey latency result.

A source-level display probe placed Capture at the center of each available monitor, then called reveal/hide three times per monitor. All six reveals stayed inside the available desktop area and Qt reported editor focus. The displays were 2560x1440 and 1920x1080, both at device pixel ratio 1.0 and 96 logical DPI. This checks explicit placement and repeated activation through Qt methods. It does not test global hotkeys from other apps on each monitor, automatic monitor selection, display removal, or mixed scaling.

The packaged executable also passed `--help` and remained running for five seconds with an empty temporary working directory, PATH limited to Windows System32, and Python/Qt environment overrides removed before selecting Qt's offscreen backend. It produced no stdout or stderr during startup. This reduces dependence on development paths; it does not replace a test on Windows without Python or developer runtimes installed.

### Browse startup and memory comparison

Run the repeatable Windows probe with:

```powershell
.venv/Scripts/python.exe scripts/benchmark_browse.py
```

The script creates temporary synthetic notes, opens each toolkit's current Browse window in a fresh process, and closes it after a two-second idle interval. It never loads personal configuration or registers hotkeys. Raw measurements and medians are written to `build/qt-prototype/browse-benchmark.json`. The default is three runs per toolkit and note count, with toolkit order reversed on alternate runs.

| Synthetic notes | Window | Median startup | Idle working set | Idle private memory |
| --- | --- | --- | --- | --- |
| 0 | Tk Browse | 698 ms | 44.2 MiB | 25.3 MiB |
| 0 | Qt Browse | 597 ms | 73.3 MiB | 33.8 MiB |
| 1,000 | Tk Browse | 8,807 ms | 85.9 MiB | 65.5 MiB |
| 1,000 | Qt Browse | 721 ms | 74.7 MiB | 35.2 MiB |

These results use Python 3.14.0 on the development Windows machine. Startup spans subprocess launch, imports, window construction, and an initial event-processing pass. It is not a measurement of the first displayed frame. OS caches were not flushed, so these are fresh-process measurements, not cold-boot results. Neither probe starts tray or hotkey services. Qt uses the Browse class directly without the runtime stylesheet. Tk has editing, tag controls, and one widget tree per note; Qt currently has a read-only list model. Feature differences limit any conclusion about the frameworks alone.

Qt uses more memory for an empty Browse window, but the current implementation opens a thousand-note list much faster and uses less memory than the Tk implementation. Repeat after feature parity before setting a production performance budget.

### Diagnostic bundle inventory

Before notices were added, the Windows payload contained 276 files totaling 117.9 MiB. Its Qt DLLs are Qt6Core, Qt6Gui, Qt6Widgets, Qt6Network, and Qt6Svg. The last two are present despite the prototype directly using only Core/Gui/Widgets. The package also includes PySide6 and Shiboken runtime files, Python, native runtime libraries, translations, and Qt plugins.

The 20 bundled plugin DLLs are:

- Generic: qtuiotouchplugin.
- Icon engines: qsvgicon.
- Image formats: qgif, qicns, qico, qjpeg, qsvg, qtga, qtiff, qwbmp, qwebp.
- Network information: qnetworklistmanager.
- Platforms: qdirect2d, qminimal, qoffscreen, qwindows.
- Styles: qmodernwindowsstyle.
- TLS: qcertonlybackend, qopensslbackend, qschannelbackend.

The initial artifact had no LICENSE, COPYING, or NOTICE files. `scripts/build_qt.py` now runs `scripts/qt_notices.py` after a successful build. It adds a `notices` directory with the project license, Python's license, installed runtime dependency notices, and the PyInstaller bootloader license. The collector follows active package requirements from PySide6 Essentials, pynput, and Pillow. It also includes the LGPLv3 and GPLv3 texts from the pinned Qt 6.11.2 source release, with upstream URLs and SHA-256 checksums in `third_party/qt-6.11.2/sources.json`. Collection itself uses local files and does not require network access.

The Qt wheels declare open-source options in metadata but include only a commercial-license reference in their installed notice files. The collector preserves that file unchanged and explains the distinction in its README. Including it does not assert a commercial Qt license.

`notices/inventory.json` records installed dependency versions, declared licenses, available notice files, and hashes for the original bundle payload. It explicitly records incomplete review status. A version mismatch or changed pinned license aborts collection. Missing installed notices are reported as unresolved. Seven focused tests cover collection, hashes, unsafe paths, version changes, and integration with successful/failed builds. The collector was also run against the existing Windows artifact. Its executable payload was not rebuilt in this pass because the user's native-test instance remained open.

This is a diagnostic inventory, not a complete SBOM or license review. Qt's nested third-party attributions, native DLLs, source availability, and other applicable distribution requirements still require verification before publishing. See [Qt third-party code](https://doc.qt.io/qt-6.11/licenses-used-in-qt.html), [Qt SBOM documentation](https://doc.qt.io/qt-6.11/sbom.html), and [Qt's LGPL guidance](https://www.qt.io/development/open-source-lgpl-obligations).

## Remaining before closing #57

- Measure native hotkey-to-input latency and verify focus from a browser and terminal, plus repeated global-hotkey activation.
- Verify hotkeys across both monitors, mixed display scales, and display disconnection. Explicit placement at 100% scaling has passed.
- Compare full application idle memory and cold launch against Tk at equivalent functionality. The source Browse comparison above is complete.
- Run the packaged application on a clean Windows machine without Python and validate other supported desktop platforms.
- Complete the module/license review and supply the remaining native-library and Qt third-party notices. The bundle now includes the locally available notices and pinned Qt license texts.

No Windows Sandbox executable or VirtualBox/VMware command was found in the checked locations on this host. Clean-machine validation still needs a separate environment.

Issue #57 remains open. The normal GUI remains Tkinter.

## Cleanup

The obsolete `docs/superpowers/plans` directory was removed at the user's request. Historical specs remain. Twelve old checkouts and stale worktree registrations were removed while retaining branch references. The `issue-13-code-quality-followups` checkout remains because Windows denies access to its old test directories; no ACL changes were made.
