# CogStash ⚡

A global hotkey brain dump — press, type, gone.

**Press `Ctrl + Shift + Space` → type your thought → hit `Enter`. Done.**

Notes are timestamped and appended to `~/cogstash.md`. Browse them later in
a card-based UI, or query from the command line.

<!-- TODO: add screenshot of capture window -->

---

## Features

- ⌨️ **Global hotkey** — capture thoughts from any app without switching windows
- 🏷️ **Smart tags** — `#todo`, `#urgent`, `#important`, `#idea` with emoji prefixes
- 🔤 **Autocomplete** — type `#` and pick a tag from the popup
- ✨ **Guided onboarding** — first-run wizard for new users plus lightweight installed-build welcome/upgrade flow
- ⚙️ **Settings window** — theme, window size, startup, hotkey, and custom tag management from the UI
- 🎨 **Themes** — 5 built-in color schemes (tokyo-night, light, dracula, gruvbox, mono)
- 🗂️ **Browse window** — card view with live search, tag filtering, safer delete preview, undo, and mark-done
- 💻 **CLI commands** — `recent`, `search`, `tags`, `add`, `edit`, `delete`, `export`, `stats`, and `config`
- 🖥️ **System tray** — runs quietly in the background with a tray icon menu
- 🌍 **Cross-platform** — Windows, macOS, and Linux

---

## Requirements

**Standalone executable:** None — just download and run.

**From source:**
- Python 3.9+
- `tkinter` (included with most Python installations)
- [`pynput`](https://pypi.org/project/pynput/) — global hotkey listener
- [`pystray`](https://pypi.org/project/pystray/) + [`Pillow`](https://pypi.org/project/Pillow/) — system tray icon

All source dependencies are installed automatically via [`uv`](https://docs.astral.sh/uv/).

---

## Installation

### Option 1: Download (no Python required)

Grab the latest release from the [**Releases page**](https://github.com/abdul219428/CogStash/releases):

| Platform | Download |
|----------|----------|
| **Windows** | `CogStash-vX.Y.Z-setup.exe`, `CogStash-vX.Y.Z-windows.exe`, `CogStash-CLI-vX.Y.Z-windows.exe`, or `CogStash-vX.Y.Z-windows.zip` |
| **macOS** | `CogStash-vX.Y.Z-macos`, `CogStash-CLI-vX.Y.Z-macos`, or `CogStash-vX.Y.Z-macos.zip` |
| **Linux** | `CogStash-vX.Y.Z-linux`, `CogStash-CLI-vX.Y.Z-linux`, or `CogStash-vX.Y.Z-linux.tar.gz` |

On Windows you can now choose between:

- `CogStash-vX.Y.Z-setup.exe` — installs `CogStash.exe` and `CogStash-CLI.exe` to `%LocalAppData%\Programs\CogStash`, adds an Apps & Features entry, creates Start Menu/Desktop shortcuts only for the UI app, and can optionally enable launch at sign-in plus add the installed CLI directory to `PATH` during setup.
- `CogStash-vX.Y.Z-windows.exe` — portable onefile executable; download and run without installing.
- `CogStash-CLI-vX.Y.Z-windows.exe` — portable CLI executable for shell-only usage.

### Which Download Should I Choose?

| If you want... | Choose... |
|----------------|-----------|
| the easiest Windows setup with shortcuts, uninstall support, and optional `PATH` / startup integration | `CogStash-vX.Y.Z-setup.exe` |
| the normal UI app without installing anything | `CogStash-vX.Y.Z-windows.exe` |
| the CLI only for shell workflows | `CogStash-CLI-vX.Y.Z-windows.exe` |
| the UI app as an extracted folder instead of a single file | `.zip` / `.tar.gz` onedir bundle |
| macOS or Linux UI app | `CogStash-vX.Y.Z-macos` or `CogStash-vX.Y.Z-linux` |
| macOS or Linux CLI only | `CogStash-CLI-vX.Y.Z-macos` or `CogStash-CLI-vX.Y.Z-linux` |

> **Tip:** The `.zip` / `.tar.gz` files are UI onedir bundles (a folder with all files).
> They start slightly faster but aren't a single portable file.

> **Uninstall note (Windows installer):** uninstall removes the installed app, installer-managed `PATH` entry, the CogStash startup script if present, shortcuts, and uninstall entry. If CogStash is still running, the installer prompts you to close it first. Your personal notes, config, and log files are kept by default.
>
> **Installed-launch note:** new users still get the full first-run wizard. The installed Windows app shows a lightweight installer welcome for installed-app upgrades and for a first installed launch over an existing config from a portable or source run.

### Option 2: From source (with uv)

```bash
# Clone the repo
git clone https://github.com/abdul219428/CogStash.git
cd CogStash

# Install uv (if not already installed)
# Windows: winget install astral-sh.uv
# macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (automatically creates .venv/)
uv sync
```

---

## Quick Start

```bash
# If using the Windows portable executable:
./CogStash-vX.Y.Z-windows.exe

# If using the standalone CLI executable:
./CogStash-CLI-vX.Y.Z-windows.exe --help

# If using the Windows installer:
# Launch CogStash from the Start Menu after setup
# Or, if you selected the PATH option during setup, run: CogStash-CLI.exe --help
# Otherwise run %LocalAppData%\Programs\CogStash\CogStash-CLI.exe from a shell

# If installed from source with uv:
uv run cogstash

# CLI dispatch also works through the package module:
python -m cogstash --help
```

### Quick Verification After Download or Install

Use the shortest check that matches what you downloaded:

| Artifact | Verify with |
|----------|-------------|
| Windows installer | Launch **CogStash** from Start Menu, confirm the tray icon appears, then run `CogStash-CLI.exe --help` if you enabled the installer `PATH` option |
| Windows portable UI | Run `./CogStash-vX.Y.Z-windows.exe`, confirm the tray icon appears, then press the hotkey once |
| Windows portable CLI | Run `./CogStash-CLI-vX.Y.Z-windows.exe --help` and `./CogStash-CLI-vX.Y.Z-windows.exe --version` |
| macOS / Linux UI binary | Run the UI binary, confirm it stays running and shows the tray / menu-bar presence supported by your desktop |
| macOS / Linux CLI binary | Run `./CogStash-CLI-vX.Y.Z-<platform> --help` and `--version` |
| source install | Run `uv run cogstash` for the UI or `python -m cogstash --help` for CLI dispatch |

If the UI starts cleanly, the tray/menu icon stays present, and the default hotkey opens the capture window, the installation is working.

CogStash starts in the system tray. Press the hotkey to capture a note:

| Key | Action |
|-----|--------|
| `Ctrl + Shift + Space` | Open the capture window |
| `Enter` | Save note and close window |
| `Shift + Enter` | Insert a new line (multi-line note) |
| `Escape` | Dismiss window without saving |

Notes are written to `~/cogstash.md` in this format:

```
- [2026-03-27 14:30] Remember to buy milk
- [2026-03-27 14:31] ☐ Review pull request #42 #todo
- [2026-03-27 14:32] 💡 What if we cached the API response? #idea
  Could save 200ms per request on the hot path.
  Worth benchmarking with production traffic.
```

Multi-line notes use 2-space indented continuation lines.

New users see the first-run wizard on their first launch. After that, use the tray icon to open:

- **Browse Notes** for searching, filtering, editing, and marking notes done
- **Settings** for theme, window size, startup, hotkey, and tag preferences

---

## Smart Tags

Type `#` in the capture window to trigger autocomplete. Four built-in tags
are recognized with special emoji prefixes:

| Tag | Prefix | Purpose |
|-----|--------|---------|
| `#todo` | ☐ | Actionable task (can be marked done later) |
| `#urgent` | 🔴 | Needs immediate attention |
| `#important` | ⭐ | High-value note |
| `#idea` | 💡 | Creative thought or suggestion |

Tags can appear anywhere in the note text. Multiple tags per note are supported.

---

## CLI Commands

CogStash includes a command-line interface for querying notes without opening
the GUI. Release builds ship it as `CogStash-CLI` alongside the UI app.
Examples below use `cogstash`; when using packaged binaries, replace that with
`CogStash-CLI.exe` on Windows or the platform-specific CLI binary from the release.

| Command | Purpose |
|---------|---------|
| `recent` | Show recent notes |
| `search` | Full-text search |
| `tags` | List tags with counts |
| `add` | Add a note from arguments or piped stdin |
| `edit` | Edit a note by number or `--search` |
| `delete` | Delete a note by number or `--search` |
| `export` | Export all notes as JSON, CSV, or Markdown |
| `stats` | Show note and tag statistics |
| `config` | Launch the config wizard or get/set supported config keys |

### `cogstash recent`

Show the most recent notes (newest first).

```bash
cogstash recent            # last 20 notes (default)
cogstash recent --limit 5  # last 5 notes
cogstash recent --tag todo # last todo notes only
```

### `cogstash search`

Full-text search across all notes. Case-insensitive, multi-word AND matching.

```bash
cogstash search "buy milk"        # notes containing "buy" AND "milk"
cogstash search "todo" --limit 10 # limit results
cogstash search "deploy" --tag urgent
```

### `cogstash tags`

List all tags with usage counts, sorted by frequency.

```bash
cogstash tags
```

Example output:

```
  todo         12
  idea          7
  urgent        3
  important     2
```

> **Note:** Output is ANSI-colored when writing to a terminal. Colors are
> automatically disabled when piping to a file or another command.

### `cogstash add`

Add a note directly from the shell. If you omit the note text, pipe it through stdin.

```bash
cogstash add "Ship the installer follow-up" # direct text
echo "Follow up with portable users" | cogstash add
```

### `cogstash edit`

Edit a note's text.

Use a note number or `--search` to target the note. When using `--search`, the replacement text follows the search term.

```bash
cogstash edit 42 "Updated note text"
cogstash edit --search "installer" "Updated note text"
```

### `cogstash delete`

Delete a note.

Use a note number or `--search` to target the note. The command asks for confirmation unless `--yes` is provided.

```bash
cogstash delete 42
cogstash delete --search "installer" --yes
```

### `cogstash export`

Export all notes to JSON, CSV, or Markdown. Without `--output`, CogStash writes an auto-named export file in the current working directory.

```bash
cogstash export --format json
cogstash export --format csv --output notes.csv
cogstash export --format md --output notes.md
cogstash export --format json --tag todo --output todo-notes.json
```

### `cogstash stats`

Show totals, streaks, tag counts, and related note statistics.

```bash
cogstash stats
```

### `cogstash config`

View configuration values, update supported keys, or launch the interactive wizard.

`cogstash config` with no action starts the interactive wizard. Press Enter to keep current value.

```bash
cogstash config
cogstash config get theme
cogstash config set window_size wide
```

> **Note:** `cogstash config get` supports `hotkey`, `theme`, `window_size`,
> `output_file`, `log_file`, and `tags`. `cogstash config set` supports
> `hotkey`, `theme`, `window_size`, `output_file`, and `log_file`. Tags are
> not writable via `config set`.
>
> Internal bookkeeping keys are not exposed through this command.

---

## Browse Window

Open the Browse window from the system tray icon → **"Browse Notes"**.

<!-- TODO: add screenshot of browse window -->

**Features:**

- 📇 **Card view** — each note displayed as a card with colored left border
- 🔍 **Live search** — filter notes as you type (200ms debounce)
- 🏷️ **Tag filter pills** — click All, #todo, #urgent, #important, or #idea
- ✅ **Mark done** — check off `#todo` items (☐ → ☑, with strikethrough)
- 📅 **Date headers** — notes grouped by TODAY, YESTERDAY, or date label
- 📊 **Footer** — shows total note count and open todo count

---

## Themes

CogStash ships with 5 color themes. Set your preference in the config file.

| Theme | Description |
|-------|-------------|
| `tokyo-night` | Dark blue-gray (default) |
| `light` | Clean white background |
| `dracula` | Dark purple palette |
| `gruvbox` | Warm retro dark theme |
| `mono` | Minimalist gray-on-black |

### Window Sizes

| Preset | Width |
|--------|-------|
| `compact` | 320 px |
| `default` | 400 px |
| `wide` | 520 px |

---

## Configuration

CogStash reads settings from `~/.cogstash.json`. The file is created
automatically on first run with default values.

| Key | Default | Description |
|-----|---------|-------------|
| `hotkey` | `<ctrl>+<shift>+<space>` | Global hotkey combination |
| `output_file` | `~/cogstash.md` | Path to the notes file |
| `log_file` | `~/cogstash.log` | Path to the log file |
| `theme` | `tokyo-night` | Color theme |
| `window_size` | `default` | Capture window size preset |
| `launch_at_startup` | `false` | UI-managed Windows startup preference |
| `last_seen_version` | `""` | Internal UI state for first-run / What's New flow |
| `last_seen_installer_version` | `""` | Internal installer-onboarding state |

Example config:

```json
{
  "hotkey": "<ctrl>+<shift>+<space>",
  "theme": "dracula",
  "window_size": "wide"
}
```

Only include the keys you want to override — missing keys use defaults.

> **Note:** `cogstash config get` supports `hotkey`, `theme`, `window_size`,
> `output_file`, `log_file`, and `tags`. `cogstash config set` supports
> `hotkey`, `theme`, `window_size`, `output_file`, and `log_file`. The
> installer/onboarding keys are maintained by the app and installer.
>
> On Windows, launch-at-startup is managed by the installer/UI startup entry as
> well as config state, so changing JSON alone is not the recommended way to
> control it.

---

## Cross-Platform Notes

CogStash runs on any system with Python 3.9+ and `tkinter`:

| OS | Notes file location |
|----|---------------------|
| Windows | `C:\Users\<you>\cogstash.md` |
| macOS | `/Users/<you>/cogstash.md` |
| Linux | `/home/<you>/cogstash.md` |

**macOS:** You may need to grant accessibility permissions for the global
hotkey to work. Go to System Settings → Privacy & Security → Accessibility
and add your terminal or Python.

**Linux:** Requires an X11 or Wayland session with `tkinter` support.
Some minimal desktop environments may need `python3-tk` installed separately.

---

## Development

```bash
# Install with dev dependencies (ruff, mypy, pytest, etc.)
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

---

## License

This project is licensed under the MIT License.

See [`LICENSE`](LICENSE) for the full text.

## Experimental Qt Widgets UI

A separate PySide6 capture-and-Browse prototype is available. The normal app still uses Tkinter. See [prototype setup and validation](docs/qt-prototype.md) for commands and current limitations.
