# Qt Widgets prototype

The experimental Qt UI tracks #57 through #60. The normal GUI still uses Tkinter. The prototype has capture, Browse with note actions, settings, onboarding, tray actions, and a global-hotkey adapter. Capture provides configured-tag autocomplete, multiline growth, and size presets. Installed startup integration and production cutover are still pending.

## Run

The Qt extra requires Python 3.10 or newer. The tested local pair is Python 3.14.0 with PySide6 Essentials 6.11.2 on Windows 11. Existing non-Qt entry points retain their declared Python support.

```powershell
uv sync --extra dev --extra qt
uv run python -m cogstash.ui.qt --notes ./prototype-notes.md
```

Provide an explicit `--notes` or `--config` path. The prototype does not read or write the default config implicitly. `--notes` alone uses session-only settings. To persist settings, use `--config ./prototype.json`, optionally with `--notes ./prototype-notes.md`. A missing config defaults to a sibling `prototype.notes.md` file and opens setup; neither file is created until a save. Existing config files use the current core format. Explicit notes, hotkey, theme, and window-size options override the loaded values for this run and are persisted only if Settings is saved. Use `--no-hotkey` when another CogStash instance is running, or provide a different `--hotkey`. The Browse window opens at startup so errors and fallback Capture/Quit controls remain reachable. Escape hides capture and retains the draft; successful save clears it. Save failures and notes over the core's 10,000-character limit retain the input.

```powershell
uv run python scripts/build_qt.py
./dist/qt-prototype/CogStash-Qt-Prototype/CogStash-Qt-Prototype.exe --notes ./prototype-notes.md
```

This is a console-enabled onedir diagnostic build. Production build targets and installer payloads are unchanged. No release has been published.

## Architecture

- `ui/qt/__main__.py` parses prototype-only options and imports Qt lazily.
- `ui/qt/app.py` creates one QApplication and defines capture and shared theme setup.
- `ui/qt/browse.py` owns the note model, card delegate, filters, edit dialog, and note actions.
- `ui/qt/runtime.py` owns lazy, reused windows and QSystemTrayIcon actions.
- `ui/qt/settings.py` owns draft settings, checked persistence through the core serializer, and onboarding selection using existing installer helpers.
- `ui/qt/hotkeys.py` owns the pynput listener and a Qt timer that checks for asynchronous listener failure.
- Background hotkey callbacks emit a queued Qt signal. They do not operate on widgets.
- Existing core parsing, saving, and search functions are reused without changes.
- PySide6 Essentials is optional; QtCharts, Qt Graphs, QML, and Qt Quick are excluded from the prototype build.
- Listener failures open Browse with actionable feedback. A live listener does not prove that every application or desktop permits global capture; native platform validation remains necessary.

## Settings and onboarding migration for #60

Settings opens from Browse or the tray. General, Appearance, and Tags tabs provide notes-file selection, hotkey syntax checking, theme and capture size choices, and custom tag editing. All changes stay in a draft until Save. Cancel and Escape do not change files or runtime settings. Saving updates the existing capture and Browse windows while preserving capture text and search filters. Configured tags reach capture suggestions, Markdown emoji rendering, and Browse filters. Tag colors remain in the core configuration format; Browse cards retain their theme foreground colors.

A changed global hotkey takes effect on restart, matching the existing Tk behavior. The syntax check does not register a second listener or claim that OS permissions or shortcut conflicts were tested. Notes-file changes are blocked during a capture draft or open note edit. A successful file switch clears the previous file's delete-undo record. Application Quit asks before discarding unsaved settings.

Persistence stages the existing core serializer into a unique sibling file and replaces the destination after successful serialization. It preserves unrelated fields and unknown top-level keys. A failed save keeps the dialog draft and original file. Changes to the config while the dialog is open cause a conflict message rather than an overwrite. This is optimistic conflict detection, not cross-process locking. Invalid paths, malformed config containers, invalid tag rows, and write failures receive feedback. The core config implementation remains unchanged.

A config with no recorded version opens setup using the same settings controls plus a capture/Browse introduction. Existing configs select installed-build welcome or ordinary upgrade welcome using the existing installer conditions. Completing setup or acknowledging welcome records the current version only after a successful save. Cancel does not record completion. Existing configurations require no format migration.

Startup is deliberately read-only in this optional prototype. On Windows, its checkbox reflects the actual installer-managed startup script without modifying it or the stored setting on open. Other platforms show the unsupported state. The production helper still launches the Tk entry point, and the diagnostic Qt executable requires explicit paths. Enabling or disabling startup belongs with the installed Qt launch contract in #61. Issue #60 therefore remains open for startup integration and native acceptance.

Validation for this slice:

- Full local suite: 440 passed, including 48 settings/onboarding cases. Ruff and mypy passed.
- Tests cover save/cancel, unknown-field retention, failed serialization/replacement, external edits, notes-path validation, tags, hotkey syntax feedback, onboarding selection, version acknowledgement, read-only startup state, live runtime updates, draft guards, and explicit config CLI options.
- Rendered all three tabs in all five themes and inspected the screenshots. Native screen-reader operation, physical keyboard/focus behavior, and mixed-monitor scaling remain pending.
- The Windows diagnostic build is isolated under `dist/qt-settings`, leaving the earlier running prototype untouched. Packaged help and startup checks use temporary notes/config files and disable the global hotkey.
- Settings regressions are included in the Windows and Ubuntu Qt CI jobs. No production installer or default GUI entry point changed.

The following sections retain the earlier migration measurements and behavior as historical snapshots.

## Browse migration for #59

Browse now uses a QListView, NoteModel, and a card delegate. Cards paint timestamps, multiline note text, tags, and completed-state strikethrough without constructing a widget tree for every note. The layout cache is bounded to the current width/font and clears on model changes. Cards stay within the viewport when the scrollbar appears or the window resizes. Selected text uses a contrasting foreground in every supported theme.

Search retains the core's case-insensitive AND behavior. The tag selector includes built-in and discovered tags with core tag counts. Active filters have visible feedback, a clear action, and distinct empty states. Existing search/tag selections survive reloads. File-read failures remain visible instead of appearing as an empty successful result.

Select a note to use Edit, Mark done, Delete, or Copy text. F2 edits, Ctrl+D marks a todo done, Delete opens confirmation, and Ctrl+C copies while the note list has focus. Double-click edits; right-click opens the same actions. Escape closes Browse. Editor shortcuts do not trigger note actions. Edit dialogs retain input after failed or stale mutations, and Browse close/application Quit can preserve unsaved edits. After editing or marking done, selection stays on that note; if an edit removes it from the current filter, note actions are disabled until another note is selected.

Mutations reuse existing core functions. The Qt layer verifies timestamp, text, and line position before invoking them, reloads actual disk contents after success, and maps each MutationStatus to feedback. This catches same-minute stale edits that the core's timestamp-only check can miss. It is an optimistic check, not cross-process file locking.

Delete previews up to three lines and 180 characters as plain text, with No as the default. Undo restores the most recent successful deletion for the session, including continuation lines. It preserves newly appended notes, but refuses intervening edits or reordering that invalidate the saved file baseline. A failed restore retains the undo record for retry. This is deliberately stricter than Tk's insertion at an old line number, which can place restored text inside a changed note. The Markdown format and core mutation implementations are unchanged.

Validation for this slice:

- Full local suite: 392 passed, including 24 Browse regression cases. Ruff and mypy passed.
- Rendered all five themes, inspected selected/done/multiline cards, and checked resize behavior. An offscreen 150% scaling probe produced a 1140-pixel image for a 760-unit window with no horizontal overflow. Native mixed-monitor scaling and screen-reader operation remain unverified.
- A 10,000-note fixture constructed and displayed in about 459 ms; filtering to one result took about 7 ms. This was a single offscreen measurement inside an already-running QApplication, excluding process startup and imports.
- A fresh Windows diagnostic build under `dist/qt-browse` includes notices and passes packaged help and a four-second startup check.
- Browse regressions now run in both Windows and Ubuntu Qt CI jobs.

The repeatable source Browse benchmark was rerun with three fresh processes per case:

| Notes | Window | Median startup | Idle working set | Idle private memory |
| --- | --- | --- | --- | --- |
| 0 | Tk Browse | 709 ms | 44.2 MiB | 25.3 MiB |
| 0 | Qt Browse | 700 ms | 74.6 MiB | 33.8 MiB |
| 1,000 | Tk Browse | 9,107 ms | 86.1 MiB | 65.6 MiB |
| 1,000 | Qt Browse | 808 ms | 78.2 MiB | 37.5 MiB |

The method and cache/startup limitations described in the earlier comparison still apply. Qt now includes the note actions, though its layout and configuration integration differ from Tk. Results remain local measurements, not performance guarantees. Raw output is in `build/qt-browse/browse-benchmark-final.json`.

Issue #59 remains open for native accessibility/scaling acceptance and integration with the settings work in #60. This slice does not implement Note Aging, resurrection, analytics, or storage metadata.

## Lifecycle integration for #58

The runtime creates Capture and Browse only when needed and reuses their instances. Startup still opens Browse as a reachable fallback. Capture commands from pynput use queued Qt signals. Commands delivered after shutdown do nothing. Repeated listener starts do not create duplicates, and Quit stops the health timer, stops/joins the listener with a bounded retry, hides the tray, and hides open windows. Listener errors do not prevent the remaining cleanup. A backend that cannot stop within the timeout is logged and retained so it cannot be duplicated in the same runtime.

The tray offers Capture, Open notes file, Browse Notes, and Quit. Clicking the tray icon opens Capture. Settings is disabled pending #60; it never starts the Tk event loop. Closing Browse hides it when a tray is available and requests Quit otherwise. Quit asks before discarding an unsaved capture draft, with Cancel as the default. Capture's close button and Escape retain the draft.

Use `--window-size compact`, `default`, or `wide` alongside the existing `--theme` option. The editor grows with explicit newlines up to the preset limit. Default smart-tag suggestions support arrow keys, Tab, Enter, and mouse selection. Enter accepts a suggestion before saving; Shift+Enter inserts a newline; Escape dismisses suggestions before hiding capture. The prototype still does not load personal settings or custom tags. Hidden capture opens on the monitor containing the pointer; an already visible capture keeps its position.

Validation for this slice:

- Full local suite: 368 passed, including 20 new lifecycle/capture tests. Ruff and mypy passed.
- Tests cover GUI-thread delivery, duplicate-start prevention, late listener failure, partial startup cleanup, startup/shutdown races, no-tray close behavior, draft cancellation, application-driven quit, Unicode tag insertion, keyboard/mouse completion, and size limits.
- A real Windows pynput listener on a separate test shortcut started and stopped cleanly. This verifies backend startup/cleanup, not physical hotkey-to-focus behavior for the new code.
- Offscreen rendering with system fonts verified the themed capture layout and suggestion list.
- A fresh Windows diagnostic artifact was built under `dist/qt-lifecycle` to avoid replacing the still-running earlier prototype. Notices were collected. Packaged help and a four-second offscreen startup smoke check passed.

### Platform limits

On Wayland, this adapter deliberately declines global registration and opens Browse with manual Capture access. Detection is covered by a simulated environment test; no native Wayland session was available. pynput documents that XWayland only observes events from applications using XWayland, which is insufficient for a system-wide shortcut. No uinput/root fallback is attempted. On X11, a usable X server and DISPLAY are required. Native X11 integration remains unverified here.

macOS failure feedback points to Accessibility permission for the app or Python launcher. The installed pynput backend sets its trust flag inside its thread, so the adapter does not reject access based on the class's initial value. Permission-error behavior is simulated in tests; a native macOS test remains outstanding. See [pynput platform limitations](https://pynput.readthedocs.io/en/latest/limitations.html).

Issue #58 remains open for native focus and scaling acceptance, platform testing, and completion of the Settings action through #60. The earlier #57 checks below remain applicable. Tk stays the default entry point.

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
