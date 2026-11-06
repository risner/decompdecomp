"""The TUI: decompdecomp in a terminal (docs/TUI.md). `decomp serve` starts the app's server in a background thread
and this in the foreground of the same terminal (cli.py); it is one more client of the app's HTTP API, exactly like
the window's JavaScript — the API tests (tests/api/) are what keep it working.

The first version only reads: projects, the function map with its picker and search, the agents at work and the
log. Everything that changes a project is on the roadmap (docs/TUI.md).
"""

from __future__ import annotations

import sys

from .client import Client


def run(port: int, secret: str, new_code) -> bool:
    """The TUI, if this terminal can show one (Textual installed — the tui extra — and a TTY): blocks until the user
    leaves it. False when it can't, and `decomp serve` prints the address and the browser link instead. `new_code`:
    the TUI's `b`, one of decomp serve's one-time browser links (sessions.py)."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        from .app import DecompApp
    except ImportError:  # textual isn't installed: window-only users don't get it (the tui extra)
        return False
    DecompApp(Client(port, secret), new_code).run()
    return True
