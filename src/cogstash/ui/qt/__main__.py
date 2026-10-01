from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(*, installed: bool = False) -> int:
    parser = argparse.ArgumentParser(description="CogStash experimental Qt capture, Browse, and Settings")
    parser.add_argument("--notes", type=Path, help="Explicit prototype Markdown file")
    parser.add_argument("--config", type=Path, help="JSON settings file (default: ~/.cogstash.json)" if installed else "Explicit JSON settings file; no personal default is loaded")
    parser.add_argument("--hotkey")
    parser.add_argument("--no-hotkey", action="store_true", help="Disable global registration for testing")
    parser.add_argument("--theme", choices=["tokyo-night", "light", "dracula", "gruvbox", "mono"])
    parser.add_argument("--window-size", choices=["compact", "default", "wide"])
    args = parser.parse_args()
    if args.config is None and installed:
        from cogstash.core.config import get_default_config_path
        args.config = get_default_config_path()
    if args.notes is None and args.config is None:
        parser.error("provide --notes or --config")
    try:
        from cogstash.ui.qt.app import run
        from cogstash.ui.qt.settings import read_config
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            parser.exit(2, "Qt prototype requires Python 3.10+ and the qt extra: uv sync --extra qt\n")
        raise
    from cogstash.core import CogStashConfig

    path = args.config.expanduser().resolve() if args.config is not None else None
    try:
        config = read_config(path) if path is not None else CogStashConfig()
        if not installed and path is not None and not path.exists():
            config.output_file = path.with_name(path.stem + ".notes.md")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Could not load configuration: {exc}\n")
    if args.notes is not None:
        config.output_file = args.notes.expanduser().resolve()
    for key in ("hotkey", "theme", "window_size"):
        if getattr(args, key) is not None:
            setattr(config, key, getattr(args, key))
    assert config.output_file is not None
    if path is not None and config.output_file.resolve() == path:
        parser.error("notes and configuration must use different files")
    if installed:
        from cogstash.ui.windows import acquire_single_instance
        guard = acquire_single_instance()
        if guard is None:
            parser.exit(0, "CogStash is already running. Quit the existing app before launching the Qt candidate.\n")
        try:
            return run(config.output_file, config.hotkey, config.theme, not args.no_hotkey, config.window_size, config, path, installed=True)
        finally:
            guard.close()
    return run(config.output_file, config.hotkey, config.theme, not args.no_hotkey, config.window_size, config, path)


if __name__ == "__main__":
    sys.exit(main())
