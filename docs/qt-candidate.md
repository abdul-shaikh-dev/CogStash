# Qt packaging candidate

This is the opt-in packaging work for #61. The default GUI and release workflow still use Tk. The candidate provides the installed launch contract and cross-platform packaging checks needed before cutover. It is not a published release.

## Build and run

The Qt builder accepts Python 3.10 through 3.14 and uses the pinned `PySide6-Essentials==6.11.2` extra. Local Windows validation uses Python 3.14.0; packaging CI uses Python 3.13 on Windows, macOS, and Linux. These are the validated version pairs, not a claim that every supported Python/platform combination has been tested. Core, CLI, and the existing Tk app retain the Python 3.9 minimum.

```powershell
uv sync --extra dev --extra qt
uv run python scripts/build_qt.py --candidate --with-cli
uv run python scripts/smoke_qt.py
```

Outputs are isolated in `dist/qt-candidate`, with build files in `build/qt-candidate`. `--dist-dir` and `--build-dir` override those locations. The candidate uses the existing installer-compatible names `CogStash-VERSION-onedir` and `CogStash-CLI-VERSION`. It remains a console-enabled diagnostic onedir build.

The source equivalent is:

```powershell
uv run python -m cogstash.ui.qt.candidate --config ./candidate.json --notes ./candidate-notes.md --no-hotkey
```

The candidate can launch without arguments and uses `~/.cogstash.json` and the existing core defaults. To evaluate it without using personal settings, pass the explicit paths shown above. Missing settings are not created until Save. The original `python -m cogstash.ui.qt` prototype still requires explicit `--notes` or `--config`. On Windows the candidate shares the existing GUI single-instance mutex and releases it even after a startup failure. The prototype remains separate.

## Startup and installer integration

Windows candidate settings enable launch-at-sign-in controls. They read the existing installer-managed `CogStash.bat` through the shared install-state helper. An unchanged checkbox preserves the existing script. Toggling startup writes a command for this executable, or the source candidate module, with an explicit absolute config path.

Startup and config edits commit together from the dialog's perspective. If the config save fails, the prior startup script is restored. Conflicting external startup edits are preserved and reported; rollback failures tell the user to inspect Windows startup manually. Cancel makes no startup changes. Batch arguments preserve spaces, percent signs, exclamation marks, ampersands, and Unicode paths. Unsupported platforms retain the disabled control.

Compile the Windows candidate installer using the existing payload contract:

```powershell
uv run python scripts/build_installer.py --dist-dir dist/qt-candidate --build-dir build/qt-candidate --output-dir dist/qt-candidate --compiler "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"
```

The builder stages the UI as `CogStash.exe`, adds `CogStash-CLI.exe` and its `bin/cogstash.cmd` shim, and refreshes the diagnostic inventory for those final paths. Inno Setup receives absolute paths so custom staging directories work regardless of the `.iss` location. This command compiles an installer; it does not install or launch it. The installer retains its existing install identity, so actual install/upgrade/uninstall trials belong in an isolated Windows environment.

## Validation and evidence

The new CI matrix builds and smoke-tests both artifacts on Windows, macOS, and Linux. It checks CLI help/version output, first-run and existing-config UI startup, fixture preservation, and PyInstaller archive contents. CLI archives must exclude Qt, Tk, tray/hotkey packages, Pillow, and all `cogstash.ui` modules. UI archives exclude Tk, pystray, Qt QML/Quick, Charts, and Graphs. Windows also compiles the installer. CI uploads the smoke report and collected notices as validation evidence, without publishing app binaries or a release.

Local Windows results:

- Full regression suite: 461 passed. Ruff and mypy passed.
- The candidate installer compiles with Inno Setup. The renamed staged executable starts with a simulated installation marker, the CLI shim prints its version, and all staged inventory hashes match. This does not establish actual install, upgrade, PATH registration, or uninstall behavior.
- UI onedir size including diagnostic notices: 118.2 MiB. CLI onefile size: 9.1 MiB. The earlier Browse diagnostic was about 117.9 MiB; the candidate remains close to that size.
- UI help, CLI help/version, and four-second UI startup checks for new and existing configs pass without modifying the fixtures.
- A native temporary batch probe round-trips spaces, `&`, `%`, `!`, and Unicode in the config argument. It does not modify the user's Startup directory.
- Startup save/cancel, failed-write rollback, external conflicts, command selection, and instance-guard cleanup have regression coverage.
- Closing the runtime now rejects its owned modal note editor. A different test ordering exposed a Windows Qt shutdown crash when that dialog remained open; the reproducing test pair passes after cleanup.

Raw local reports and build logs are under `build/qt-candidate`. Earlier prototype latency, memory, and large-list measurements remain in [qt-prototype.md](qt-prototype.md); they are historical results, not final installed-candidate measurements.

## Remaining cutover checks

Issue #61 remains open. Before changing the default GUI or removing Tk/pystray:

- Run interactive capture/focus, tray, accessibility, and mixed-monitor checks on supported desktops. Offscreen process startup does not establish these behaviors. Wayland global capture remains unsupported by the current pynput backend.
- Verify actual Windows install, upgrade, startup at sign-in, CLI PATH selection, close-before-uninstall, and preservation of user files in an isolated environment without Python.
- Complete the license, native-library attribution, and source/replacement obligation review for the actual distributed bundle. The diagnostic inventory still records `review_status: incomplete`.
- Record final installed-candidate latency, idle memory, and large-list behavior, and compare them with the preserved baseline.
- Complete the default-entry-point and dependency removal changes after those acceptance checks. Publishing a release is a separate action.
