"""One-time links and browser sessions for `decomp serve` (cli.py).

The app with its own window never accepts these: its page answers only clients whose user agent carries the
per-launch secret (window.py), and that stays so. But a browser can't carry a secret in its user agent the way the
app's own window does, so `decomp serve` pairs instead: it shows a code once in its terminal, the link trades the
code for a session cookie, and the code is spent. Sessions live in this process's memory and end with it: after an
update restart, or a stop and a start, the browser pairs again.

What keeps a session from reaching anything the window couldn't: the server still listens on 127.0.0.1 only (reaching
it takes a login to the machine), Host headers are checked as always, writes still need the X-Decomp header — which a
page from another site can't send without a CORS preflight the server never approves — and a session starts only with
a code that was shown once in the server's own terminal.
"""

from __future__ import annotations

import secrets

COOKIE = "decomp_session"  # the browser's paired session (HttpOnly, SameSite=Strict; routes/pages.py)
WAITING_CODES = 8  # `b` in the TUI shows one after another; more than this waiting is a stuck terminal


class Sessions:
    """The codes `decomp serve` has shown and not spent, and the sessions browsers have paired."""

    def __init__(self) -> None:
        self._codes: list[str] = []
        self._tokens: list[str] = []

    def new_code(self) -> str:
        """A fresh one-time code for the terminal to show."""
        code = secrets.token_urlsafe(9)
        self._codes = (self._codes + [code])[-WAITING_CODES:]
        return code

    def spend(self, code: str) -> str:
        """Trade a one-time code for a session token. A code works once; a wrong or used one is refused."""
        for i, waiting in enumerate(self._codes):
            if secrets.compare_digest(waiting, code):
                del self._codes[i]
                token = secrets.token_urlsafe(24)
                self._tokens.append(token)
                return token
        raise ValueError("this link was used already, or is wrong: get a fresh one in the server's terminal")

    def valid(self, token: str) -> bool:
        """Whether a request's cookie names a live session (a browser that paired)."""
        return any(secrets.compare_digest(live, token) for live in self._tokens)
