"""The GUI's page, for the app's own window only (its user agent carries the per-launch secret: window.py) — or, under
`decomp serve`, a browser that paired (sessions.py) — its assets, and the health check `decomp` asks to find a running
app and its version.
"""

from __future__ import annotations

import mimetypes
import secrets

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from ... import __version__, hostenv
from .. import edition, sessions, window
from ..support import static_file
from . import App

# what the browser tab of 1.0.2 and older shows after updating into this version
OLD_PAGE = ("<!doctype html><meta charset=utf-8><title>decompdecomp</title>"
            "<body style='font:16px/1.5 system-ui;background:#0b0c0e;color:#e8e6e1;padding:3rem;max-width:46rem'>")
OLD_PAGE_LINUX = ("decompdecomp now opens in a window of its own (it just did, if it was updated): you can close this one. "
                  "Next time, use its app icon or run <code>decomp</code>.")
OLD_PAGE_WINDOWS = ("<p><b>This version of decompdecomp doesn't run on Windows.</b> Windows comes back in 1.0.4. Your projects "
                    "are safe, and update checks are now off, so 1.0.2 won't update itself again.</p>"
                    "<p>Go back to 1.0.2: in PowerShell, run</p><pre style='white-space:pre-wrap'>"
                    + hostenv.WSL_GO_BACK + "</pre><p>then start decompdecomp as before.</p>")


def register(app: App) -> None:
    mcp, secret, build_id, allowed_hosts = app.mcp, app.secret, app.build_id, app.allowed_hosts

    @mcp.custom_route("/", methods=["GET"])
    async def index(request: Request) -> Response:
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"error": "bad host"}, status_code=403)
        paired = app.sessions is not None and app.sessions.valid(request.cookies.get(sessions.COOKIE, ""))
        if not paired and not secrets.compare_digest(window.request_token(request), secret):
            return HTMLResponse(OLD_PAGE + (OLD_PAGE_WINDOWS if hostenv.in_old_windows_install() else OLD_PAGE_LINUX), status_code=401)
        return HTMLResponse(static_file("index.html").decode(), headers={"Cache-Control": "no-store"})

    @mcp.custom_route("/pair", methods=["GET"])
    async def pair(request: Request) -> Response:
        """`decomp serve`'s one-time link: a code shown once in the server's terminal becomes a session cookie, and
        the browser lands on the GUI. The app with its own window doesn't have sessions, and says so."""
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"error": "bad host"}, status_code=403)
        if app.sessions is None:
            return Response("decompdecomp isn't serving its GUI to browsers here: it has a window of its own", status_code=404)
        try:
            token = app.sessions.spend(request.query_params.get("code", ""))
        except ValueError as e:
            return Response(str(e), status_code=403)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(sessions.COOKIE, token, httponly=True, samesite="strict")
        return response

    @mcp.custom_route("/assets/{name:path}", methods=["GET"])
    async def asset(request: Request) -> Response:
        if request.headers.get("host") not in allowed_hosts:
            return Response(status_code=403)
        name = request.path_params["name"]
        data = static_file(name)
        if data is None:
            return Response(status_code=404)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return Response(data, media_type=ctype, headers={"Cache-Control": "no-cache"})

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "app": "decomp-wtf", "edition": edition.NAME, "version": __version__,
                             "build": build_id})
