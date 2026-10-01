from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="CogStash experimental Qt capture and Browse")
    parser.add_argument("--notes", type=Path, required=True, help="Explicit prototype Markdown file")
    parser.add_argument("--hotkey", default="<ctrl>+<shift>+<space>")
    parser.add_argument("--no-hotkey", action="store_true", help="Disable global registration for testing")
    parser.add_argument("--theme", choices=["tokyo-night", "light", "dracula", "gruvbox", "mono"], default="tokyo-night")
    args = parser.parse_args()
    try:
        from cogstash.ui.qt.app import run
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            parser.exit(2, "Qt prototype requires Python 3.10+ and the qt extra: uv sync --extra qt\n")
        raise
    return run(args.notes.expanduser(), args.hotkey, args.theme, not args.no_hotkey)


if __name__ == "__main__":
    sys.exit(main())
