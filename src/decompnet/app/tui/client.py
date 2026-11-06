"""The TUI's one way to its app: GET requests over HTTP on 127.0.0.1, carrying the per-launch secret in the user
agent the way the window and `decomp`'s own commands do (window.py, cli._call). The first version only reads: get().
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .. import window

TIMEOUT = 5  # a poll that hangs would freeze the screen it feeds


class Client:
    """Talks to the app the TUI runs beside (cli.run started both)."""

    def __init__(self, port: int, secret: str):
        self.base = f"http://127.0.0.1:{port}"
        self.agent = f"{window.TOKEN_AGENT}{secret}"

    def get(self, path: str, **params) -> object | None:
        """One GET and its JSON answer; None when the app didn't answer in time (restarting, or gone: the screens
        say so and try again on their next poll)."""
        ask = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v is not None)
        req = urllib.request.Request(self.base + path + ("?" + ask if ask else ""), headers={"User-Agent": self.agent})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read() or b"null")
        except (OSError, ValueError):
            return None
