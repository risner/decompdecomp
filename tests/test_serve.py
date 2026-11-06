"""`decomp serve`: the app with no window on a machine with no desktop, and the browser sessions that reach its GUI
(sessions.py). The auth matrix runs in-process against build(); starting for real, with no DISPLAY, runs the actual
`decomp serve` as a subprocess, the way a server would."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from decompnet.app import window
from decompnet.app.engine import RomNetwork
from decompnet.app.server import build
from decompnet.app.sessions import COOKIE, Sessions

PORT, SECRET = 6499, "s3cret-for-tests"


@pytest.fixture(scope="module")
def serving(tmp_path_factory):
    """The app as `decomp serve` builds it: with browser sessions, and no window of its own."""
    home = tmp_path_factory.mktemp("home")
    (home / ".decomp").mkdir()
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    sessions = Sessions()
    mcp, _, security, _ = build(net, home / ".decomp", PORT, SECRET, pair=sessions)
    app = mcp.streamable_http_app(transport_security=security, host="127.0.0.1")
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}"), sessions  # a browser: no User-Agent secret


def pair(browser: TestClient, sessions: Sessions) -> str:
    """Show a code in the server's terminal, open its link: the browser ends up with a session cookie, on the GUI."""
    code = sessions.new_code()
    redirected = browser.get(f"/pair?code={code}", follow_redirects=False)
    assert redirected.status_code == 303 and redirected.headers["location"] == "/"
    set_cookie = redirected.headers["set-cookie"].lower()
    assert COOKIE in set_cookie and "httponly" in set_cookie and "samesite=strict" in set_cookie
    assert browser.get("/").status_code == 200  # the redirect's target, with the cookie the browser now carries
    return code


def test_a_code_works_once_and_a_used_code_is_refused(serving):
    browser, sessions = serving
    assert browser.get("/pair").status_code == 403  # no code at all
    assert browser.get("/pair?code=not-a-code").status_code == 403
    code = pair(browser, sessions)
    assert browser.get(f"/pair?code={code}").status_code == 403  # spent: one code, one browser


def test_a_sessions_reads_work_and_writes_still_need_the_header(serving):
    browser, sessions = serving
    pair(browser, sessions)
    assert browser.get("/api/state").status_code == 200
    assert browser.post("/api/settings", json={"per_session": 3}).status_code == 403  # a page from another site
    assert browser.post("/api/settings", json={"per_session": 3}, headers={"X-Decomp": "1"}).status_code == 200
    evil = TestClient(browser.app, base_url=f"http://evil.example:{PORT}", cookies={COOKIE: "anything"})
    assert evil.get("/api/state").status_code == 403  # the host check doesn't lean on the secret alone


def test_the_app_with_a_window_refuses_a_session_cookie(serving, tmp_path):
    """Built without sessions — the app with its own window — a paired browser's cookie opens nothing, and /pair
    says so: only `decomp serve` accepts browsers."""
    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    mcp, _, security, _ = build(net, home / ".decomp", PORT, SECRET)
    windowed = TestClient(mcp.streamable_http_app(transport_security=security, host="127.0.0.1"),
                          base_url=f"http://127.0.0.1:{PORT}")
    browser, sessions = serving  # a real pairing, from the serving app above
    code = sessions.new_code()
    token = sessions.spend(code)
    assert windowed.get("/", cookies={COOKIE: token}).status_code == 401
    assert windowed.get("/api/state", cookies={COOKIE: token}).status_code == 401
    assert windowed.get(f"/pair?code={code}").status_code == 404


class Serve:
    """A real `decomp serve` in a subprocess of its own home, with no DISPLAY and no WAYLAND_DISPLAY, printing what
    it prints; the way it runs on a server, read here like a user would."""

    def __init__(self, home: Path):
        home.mkdir(parents=True, exist_ok=True)
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        env = dict(os.environ, DECOMP_HOME=str(home), DECOMP_PORT=str(port), DECOMP_UPDATES="off",
                   DECOMP_DETECT_AGENTS="off", DECOMP_TRAY="0", DECOMP_WINDOW="0")
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        self.lines: list[str] = []
        self.proc = subprocess.Popen([sys.executable, "-m", "decompnet.app.cli", "serve"], env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        threading.Thread(target=self._read, daemon=True).start()
        for _ in range(300):  # it answers /health once the server runs (the port it took is in server.json)
            try:
                info = json.loads((home / ".decomp" / "server.json").read_text(encoding="utf-8"))
                with httpx.Client(base_url=f"http://127.0.0.1:{info['port']}") as asking:
                    if asking.get("/health").json().get("app") == "decomp-wtf":
                        self.port, self.secret = int(info["port"]), str(info["secret"])
                        return
            except (OSError, ValueError, KeyError, httpx.HTTPError):  # not up yet, or its old file's port
                pass
            time.sleep(0.1)
        self.stop()
        raise AssertionError("decomp serve didn't start:\n" + "\n".join(self.lines))

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def link(self) -> str:
        """The one-time link it printed (b in the TUI shows a fresh one; here the first is enough)."""
        for _ in range(100):
            for line in self.lines:
                if "/pair?code=" in line:
                    return line.split()[0]
            time.sleep(0.1)
        raise AssertionError("decomp serve printed no link:\n" + "\n".join(self.lines))

    def stop(self) -> list[str]:
        try:
            self.proc.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
        else:
            return self.lines
        ask = httpx.Client(base_url=f"http://127.0.0.1:{self.port}")
        try:  # it may have ended on its own between the check above and this ask
            ask.post("/api/quit", json={}, headers={"User-Agent": f"{window.TOKEN_AGENT}{self.secret}", "X-Decomp": "1"})
        except httpx.HTTPError:
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
        return self.lines


def test_serve_starts_with_no_display_and_pairs_a_browser(tmp_path):
    serve = Serve(tmp_path / "home")
    try:
        link = serve.link()
        assert link.startswith(f"http://127.0.0.1:{serve.port}/pair?code=")
        browser = httpx.Client(base_url=f"http://127.0.0.1:{serve.port}", follow_redirects=True)
        paired = browser.get(link)  # the code is traded for a cookie, and the browser lands on the GUI
        assert paired.status_code == 200 and "<html" in paired.text.lower()
        assert browser.get("/api/projects").status_code == 200  # the session reads like the window does
        again = httpx.Client(base_url=f"http://127.0.0.1:{serve.port}")
        assert again.get(link).status_code == 403  # the code is spent: a second browser can't reuse it
        browser.close()
        again.close()
    finally:
        serve.stop()


def test_sessions_end_when_the_app_stops(tmp_path):
    """Sessions live in the app's memory: a stop ends them, and the next `decomp serve` pairs the browser again."""
    home = tmp_path / "home"
    first = Serve(home)
    browser = httpx.Client(base_url=f"http://127.0.0.1:{first.port}", follow_redirects=True)
    assert browser.get(first.link()).status_code == 200
    first.stop()
    second = Serve(home)
    try:
        old = httpx.Client(base_url=f"http://127.0.0.1:{second.port}", follow_redirects=True,
                           cookies={COOKIE: browser.cookies.get(COOKIE, "")})
        assert old.get("/").status_code == 401  # the old app's session went with the old app
        assert old.get(second.link()).status_code == 200  # a fresh link pairs again
        old.close()
    finally:
        second.stop()
    browser.close()
