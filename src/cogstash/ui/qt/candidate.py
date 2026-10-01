"""Opt-in Qt installed-launch candidate; the normal GUI remains unchanged."""
from cogstash.ui.qt.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(installed=True))
