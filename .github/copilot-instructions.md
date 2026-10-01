# CogStash — Copilot Instructions

## Project Overview

CogStash is a desktop brain-dump tool: press a global hotkey, type a thought, and it's saved. Built with Python, tkinter, pynput, and pystray.

## Architecture

- **`src/cogstash/`** — Standard Python src-layout package
  - `app.py` — Main tkinter app (CogStash class, config, themes, hotkey, tray)
  - `cli.py` — CLI commands (recent, search, tags, add, edit, delete, export, stats, config)
  - `search.py` — Pure data layer (parse, search, filter, edit, delete, stats). No GUI imports.
  - `browse.py` — Browse/search window with card view. Imports from app.py.
  - `__init__.py` — Lazy `main()` wrapper to avoid loading tkinter on import
  - `__main__.py` — `python -m cogstash` support
- **`tests/`** — pytest test suite
- **`docs/superpowers/specs/`** — Design specs for each phase
- **`docs/qt-prototype.md`** — Experimental Qt entry point, build instructions, and validation status

## Key Conventions

### Code Style
- Python 3.9+ target. Use `from __future__ import annotations` in all source files.
- Line length: 120 characters
- Linted with ruff (rules: E, F, W, I; E501 ignored)
- Type-checked with mypy (ignore_missing_imports=true for pynput/pystray/Pillow)
- UTF-8 encoding explicitly for all file operations

### Architecture Patterns
- **Lazy imports** for UI modules to avoid circular dependencies
- **`search.py` is pure data** — no tkinter or GUI imports allowed
- **`browse.py` imports from `app.py`** at module level; `app.py` lazy-imports `browse.py`
- **Queue messages**: uppercase strings ("SHOW", "BROWSE", "QUIT") for inter-thread communication
- Tags stored WITHOUT `#` prefix (e.g., `"todo"` not `"#todo"`)

### Note Format
```
- [YYYY-MM-DD HH:MM] note text #tag1 #tag2
  continuation line (indented 2 spaces)
```
- `☐` prefix = is_done=False, `☑` prefix = is_done=True

### Testing
- pytest with `conftest.py` providing shared Tk root fixture
- `@needs_display` marker for tests requiring tkinter (skipped in headless CI without xvfb)
- Use `_make_notes_file(tmp_path)` helper pattern for reusable test data
- Tests run in CI with xvfb-run on Linux across Python 3.9–3.13

### Git Commits
- NEVER add Co-authored-by trailers
- Use conventional commit prefixes: feat:, fix:, docs:, refactor:, style:, chore:, ci:
- PascalCase "CogStash" for branding, lowercase "cogstash" for filenames and code

### Dependencies
- Runtime: pynput>=1.7, pystray>=0.19, Pillow>=9.0
- Dev: pytest>=7.0, ruff>=0.4, mypy>=1.10
- Dev deps live in `[project.optional-dependencies]` in pyproject.toml
- `requirements.txt` is runtime-only

## Commands
- **Install deps**: `uv sync --extra dev`
- **Run anything**: `uv run <command>` (auto-uses managed .venv)
- **Tests**: `uv run pytest tests/ -v`
- **Lint**: `uv run ruff check src/ tests/`
- **Type check**: `uv run mypy src/cogstash/`
- **Add dep**: `uv add <package>` (runtime) / `uv add --optional dev <package>` (dev)
