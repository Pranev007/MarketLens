"""Consistent logging setup for every entry point in the project."""

from __future__ import annotations

import logging
import sys


def use_utf8_console() -> None:
    """Make stdout/stderr able to print the rupee sign on Windows.

    Windows consoles default to a legacy code page (cp1252 in most locales),
    which raises UnicodeEncodeError the first time a currency-formatted figure
    is printed. Reconfiguring to UTF-8 with replacement keeps the CLI usable
    everywhere; the report files are written as UTF-8 regardless.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # A redirected or already-detached stream; not worth failing over.
                pass


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once, with a compact, readable format."""
    use_utf8_console()
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(level)
