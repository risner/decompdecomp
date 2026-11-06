"""The app's API, described and checked, so the TUI (src/decompnet/app/tui) can't drift from it quietly.

tests/api/openapi.json is generated from the app itself — never hand-written — on a project seeded straight into the
database (no compiler, no demo ROM: it never skips). Routes and methods come from the route table the app builds;
each handler's source says what it reads (data.get("x"), data["x"], request.query_params.get("x"), unwrapping
with_project); real answers on the seeded project, reduced to field names and JSON types, say what it returns.

Every POST route must be in exactly one of tests/api/requests.json (a sample body, sent for real) or
tests/api/excluded.json (a reason: it installs software, starts processes, reaches the network or ends the app).
Every answer is also saved, as it came, to tests/api/samples/ — the TUI's own tests answer from those.

A difference between the generated description and the committed one fails here. To update them after changing the
API (and the TUI with it, where the TUI uses what changed):

    uv run pytest tests/test_api_snapshot.py --update-api

and commit the new files in tests/api/.

What the answers never contain: anything that changes between machines or runs. Times and ids are zeroed, texts the
machine writes ("<text>"), what's installed on this computer ("<varies>"), the version ("<version>"), this home's
paths ("~"). The seeded data itself is constants, so everything else is stable wherever the tests run.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import textwrap
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from decompnet import __version__
from decompnet.app import window
from decompnet.app.engine import RomNetwork
from decompnet.app.server import build

HERE = Path(__file__).parent
API = HERE / "api"
PORT, SECRET = 6498, "api-snapshot-secret"
WINDOW = {"User-Agent": f"Mozilla/5.0 AppleWebKit/605.1.15 {window.TOKEN_AGENT}{SECRET}"}
SLUG = "tui-seed"  # the seeded project every answer is asked about
CLAIMED, TRIED, SET_ASIDE = "func_80000020", "func_80000030", "func_80000050"  # what the sample bodies act on

# values no two machines or runs agree on, replaced so the committed files are stable anywhere
TEXT_KEYS = {"error", "message", "why", "said", "log"}  # the machine's own words
ID_KEYS = {"job"}  # a background job's id, new every time
VARIES_KEYS = {"installed", "missing", "detecting", "matches_per_hour", "compiles_last_hour", "current"}
VARIES_BY_ROUTE = {"/api/state": {"version", "build", "install", "platform", "system", "home", "log_file",
                                  "mcp_url", "toolchains", "agents", "agents_detecting", "bridges_removed",
                                  "settings", "consoles", "api_presets"},
                   "/api/update": {"job", "notes"}}
TIME_KEYS = {"created_at", "claimed_at", "expires_at", "matched_at", "t", "now", "last_activity", "checked"}
TIME_BY_ROUTE = {"/api/stats": {"last"}}  # (elsewhere "last" is an event id, and stable)
VERSION = re.compile(r"\d+\.\d+\.\d+(-alpha(\.\d+)?)?")

# what each GET is asked (a POST gets its body from requests.json): most need only the seeded project
QUERIES: dict[str, dict[str, str]] = {
    "/api/map": {"slug": SLUG},
    "/api/mapcolumns": {"slug": SLUG},
    "/api/project": {"slug": SLUG},
    "/api/knowledge": {"slug": SLUG},
    "/api/modelcosts": {"slug": SLUG},
    "/api/live": {"slug": SLUG, "e": "0", "a": "0"},
    "/api/function": {"slug": SLUG, "name": CLAIMED},
    "/api/diff": {"slug": SLUG, "name": CLAIMED, "which": "latest"},
    "/api/stats": {"slug": SLUG},
    "/api/compilermap": {"slug": SLUG},
    "/api/fork/needs": {"slug": SLUG},
    "/api/endpoints/models": {"id": "none"},
    "/api/events": {"after": "0"},
    "/api/job": {"id": "none"},
    "/api/log": {},
}
# routes that start background work touching the project: called last, so nothing after them reads what they change
LAST_CALLS = {"/api/export", "/api/recheck", "/api/save"}


def seed(net: RomNetwork, home: Path) -> None:
    """A project with a function in every status the map shows, a claim, attempts, an event; one project that can't
    be read; one for /api/delete's sample body to remove. Straight into the database: the API answers it as it would
    a real import's, without needing a compiler or a demo ROM."""
    (home / "tui-root").mkdir(parents=True, exist_ok=True)
    with net.store.tx() as db:
        db.execute("INSERT INTO agents(id, name, owner, token_hash) VALUES(1, 'claude-3', 'local', 'seed-1')")
        db.execute("INSERT INTO projects(id, slug, name, arch, root, config) VALUES(1, ?, 'TUI Seed', 'mips', ?, ?)",
                   (SLUG, str(home / "tui-root"), json.dumps(
                       {"kind": "rom", "platform": "n64",
                        "compiler": {"toolchain": "gcc-2.7.2-kmc", "flags": []},
                        "rom": {"title": "TUI Seed", "game_code": "TSED", "region": "E", "size": 1048576,
                                "sha1": "0" * 40, "byte_order": "big"}})))
        db.execute("INSERT INTO projects(id, slug, name, arch, root, config) VALUES(2, 'tui-broken', 'Broken', "
                   "'mips', ?, '{}')", (str(home / "gone"),))
        db.execute("INSERT INTO projects(id, slug, name, arch, root, config) VALUES(3, 'delete-me', 'Gone Soon', "
                   "'mips', ?, '{}')", (str(home / "delete-me"),))
        # status and what the map makes of it: polished and plain matches, a claim, tried, not-C (both kinds), open
        rows = [  # name, vram, insns, status, best, attempts, matched_by, matched_at, readable, meta
            ("func_80000000", 0x80000000, 132, "matched", 0, 4, 1, 1700000000.0, 1, None),
            ("func_80000010", 0x80000010, 12, "matched", 0, 7, 1, 1700000100.0, 0, None),
            (CLAIMED, 0x80000020, 64, "open", None, 0, None, None, 0, None),
            (TRIED, 0x80000030, 28, "open", 400, 2, None, None, 0, None),
            ("func_80000040", 0x80000040, 220, "asm", None, 9, None, None, 0, '{"not_c": true}'),
            (SET_ASIDE, 0x80000050, 44, "asm", None, 1, None, None, 0, None),
            ("func_80000060", 0x80000060, 8, "open", None, 0, None, None, 0, None),
            ("func_80000070", 0x80000070, 500, "open", None, 0, None, None, 0, None)]
        for i, (name, vram, insns, status, best, tries, by, at, readable, meta) in enumerate(rows):
            db.execute("INSERT INTO functions(id, project_id, name, vram, size, n_insns, asm, relocs, status, "
                       "best_score, attempts, unit, matched_agent_id, matched_at, readable, meta) "
                       "VALUES(?, 1, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?, ?)",
                       (i + 1, name, vram, insns * 4, insns, "jr $ra", status, best, tries,
                        "main.c" if i % 2 else "math.c", by, at, readable, meta))
        db.execute("INSERT INTO claims(function_id, agent_id, claimed_at, expires_at) VALUES(3, 1, 1700000200.0, "
                   "4102444800.0)")  # far future: an expired claim would vanish between runs
        db.execute("INSERT INTO context_versions(project_id, version, header, message, created_at) "
                   "VALUES(1, 1, '', 'seeded', 0)")  # an import writes one; the overview reads its version
        db.execute("INSERT INTO attempts(id, function_id, agent_id, score, compiled, created_at) VALUES"
                   "(1, 4, 1, 400, 1, 1700000300.0), (2, 4, 1, 900, 1, 1700000400.0)")
        db.execute("INSERT INTO events(id, project_id, agent_id, kind, detail, created_at) VALUES"
                   "(1, 1, 1, 'match', 'func_80000010 matched', 1700000500.0)")


def unwrap(endpoint) -> object:
    """with_project's fn(slug, request, data), from the handler it wraps; the handler itself when nothing is wrapped."""
    for cell in endpoint.__closure__ or ():
        inside = getattr(cell, "cell_contents", None)
        if inspect.isfunction(inside) and inside is not endpoint:
            args = inside.__code__.co_varnames[:inside.__code__.co_argcount]
            if args == ("slug", "request", "data"):
                return inside
    return endpoint


def inputs_of(endpoint) -> tuple[list[str], list[str]]:
    """The names a handler reads from the body and from the query: the literal strings in data.get("x"), data["x"]
    and request.query_params.get("x") — under whatever name either arrives (`q = request.query_params`, a
    with_project fn's `r`)."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(unwrap(endpoint))))
    except (OSError, TypeError, SyntaxError):
        return [], []
    body, query = set(), set()
    aliases = set()  # names standing for request.query_params
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) and node.value.attr == "query_params":
            aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f, args = node.func, node.args
            if isinstance(f, ast.Attribute) and f.attr == "get" and args and isinstance(args[0], ast.Constant):
                on = f.value
                if isinstance(on, ast.Name) and on.id == "data":
                    body.add(args[0].value)
                elif isinstance(on, ast.Name) and on.id in aliases:
                    query.add(args[0].value)
                elif isinstance(on, ast.Attribute) and on.attr == "query_params" and isinstance(on.value, ast.Name):
                    query.add(args[0].value)  # request.query_params.get(...) — or r.query_params.get(...)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "data":
            if isinstance(node.slice, ast.Constant):
                body.add(node.slice.value)
    return sorted(body), sorted(query)


def sanitize(value, path: str, home: Path):
    """What no two machines or runs agree on, replaced so the committed files are stable anywhere."""
    varies = VARIES_KEYS | VARIES_BY_ROUTE.get(path, set())
    times = TIME_KEYS | TIME_BY_ROUTE.get(path, set())

    def walk(v, key: str | None):
        if key in varies:
            return "<varies>"
        if key in TEXT_KEYS and isinstance(v, str):
            return "<text>"
        if key in ID_KEYS:
            return "<id>"
        if key in times and isinstance(v, (int, float)) and not isinstance(v, bool):
            return 0
        if isinstance(v, dict):
            return {k: walk(w, k) for k, w in v.items()}
        if isinstance(v, list):
            return [walk(w, key) for w in v]
        if isinstance(v, str):
            return "<version>" if VERSION.fullmatch(v) else v.replace(str(home), "~")
        return v

    return walk(value, None)


def shape(value):
    """A value as field names and JSON types (a list by its items' shapes, merged; null beside what it sits beside)."""
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array", "items": merge(*[shape(v) for v in value]) if value else None}
    return {"type": "object", "properties": {k: shape(v) for k, v in sorted(value.items())}}


def merge(*shapes):
    """Shapes of the same thing seen more than once (a list's items, two calls): one shape that covers both."""
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    out = shapes[0]
    for other in shapes[1:]:
        if out == other:
            continue
        if all(s.get("type") == "object" for s in (out, other)):
            props = {**out.get("properties", {}), **other.get("properties", {})}
            both = set(out.get("properties", {})) & set(other.get("properties", {}))
            out = {"type": "object", "properties": {k: (merge(props[k]) if k in both else props[k])
                                                    for k in sorted(props)}}
        elif all(s.get("type") == "array" for s in (out, other)):
            out = {"type": "array", "items": merge(out.get("items"), other.get("items"))}
        else:
            kinds = sorted({t for s in (out, other)
                            for t in ([s["type"]] if isinstance(s.get("type"), str) else s.get("type", []))})
            out = {"type": kinds if len(kinds) > 1 else kinds[0]}
    return out


def rows_by_name(sample, keys_field: str = "keys") -> object:
    """/api/map (and mapcolumns) send rows as arrays under `keys`: the shape describes them by those field names,
    which is how the TUI (and everything else) must read them."""
    if isinstance(sample, dict) and sample.get(keys_field) and sample.get("rows"):
        sample = dict(sample)
        keys = sample[keys_field]
        sample["rows"] = [dict(zip(keys, row)) for row in sample["rows"]]
    return sample


def describe(tmp: Path) -> tuple[dict, dict, set]:
    """Build the app on a throwaway home, seed it, walk its routes and ask each one: the description and every answer
    as it came (sanitized). One pass, in a fixed order, so what the calls change is part of the description too."""
    home = tmp / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    seed(net, home)
    mcp, _, security, _ = build(net, home / ".decomp", PORT, SECRET)
    app = mcp.streamable_http_app(transport_security=security, host="127.0.0.1")
    client = TestClient(app, base_url=f"http://127.0.0.1:{PORT}", headers=WINDOW)
    requests = json.loads((API / "requests.json").read_text(encoding="utf-8"))

    table: dict[tuple[str, str], object] = {}  # (method, path) -> endpoint, the app's own route table
    for route in app.routes:
        if str(getattr(route, "path", "")).startswith("/api/"):
            for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}):
                table[(method, route.path)] = route.endpoint

    paths: dict[str, dict] = {}
    samples: dict[str, object] = {}
    order = sorted(table, key=lambda mp: (mp[1] in LAST_CALLS, mp[1], mp[0]))  # background-starters last
    for method, path in order:
        endpoint = table[(method, path)]
        body, query = inputs_of(endpoint)  # what it reads, called or not: an excluded route still says its inputs
        if unwrap(endpoint) is not endpoint:
            body = sorted(set(body) | {"slug"})  # with_project reads the project itself
        body = sorted(set(body) | set(requests.get(path, {}).get("fields", [])))
        entry = {"summary": ((endpoint.__doc__ or "").strip().split("\n")[0]),
                 "query": query, "body": body, "called": False}
        sample = None
        if method == "GET":
            answer = client.get(path, params=QUERIES.get(path, {"slug": SLUG}))
            if path == "/api/log":
                sample = answer.text
            else:
                data = answer.json()
                if path == "/api/map" and data.get("sig"):  # the poll every few seconds: nothing changed is an answer too
                    data["unchanged"] = client.get(path, params={"slug": SLUG, "since": data["sig"]}).json()
                sample = sanitize(data, path, home)
        elif path in requests:
            answer = client.post(path, json=requests[path]["body"], headers={"X-Decomp": "1"})
            sample = sanitize(answer.json() if answer.headers.get("content-type", "").startswith("application/json")
                              else answer.text, path, home)
        if sample is not None:
            entry["called"] = True
            entry["response"] = shape(rows_by_name(sample)) if not isinstance(sample, str) \
                else {"type": "string", "format": "text"}
            if path == "/api/map":  # the statuses the TUI paints cells by: a new one must fail here too
                named = rows_by_name(sample)["rows"]
                entry["response-values"] = {"status": sorted({row["status"] for row in named})}
            samples[path.lstrip("/").replace("/", "_") + ".json"] = sample
        paths.setdefault(path, {})[method.lower()] = entry
    doc = {"openapi": "3.1.0", "info": {"title": "decompdecomp's API", "version": __version__,
                                        "x-generated": "tests/test_api_snapshot.py --update-api"},
           "paths": {p: paths[p] for p in sorted(paths)}}
    return doc, samples, {path for method, path in table if method == "POST"}


def dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    return describe(tmp_path_factory.mktemp("api-snapshot"))


def test_the_api_description_matches_the_committed_one(generated, request):
    doc, samples, _ = generated
    if request.config.getoption("--update-api"):
        (API / "samples").mkdir(parents=True, exist_ok=True)
        (API / "openapi.json").write_text(dump(doc), encoding="utf-8")
        for old in (API / "samples").glob("*.json"):
            old.unlink()
        for name, sample in sorted(samples.items()):
            (API / "samples" / name).write_text(dump(sample), encoding="utf-8")
        return
    assert (API / "openapi.json").exists(), "tests/api/openapi.json is missing: generate it with --update-api"
    if (API / "openapi.json").read_text(encoding="utf-8") != dump(doc):
        print("\nThe app's API changed. Update the TUI (src/decompnet/app/tui) to match, run\n"
              "uv run pytest tests/test_api_snapshot.py --update-api, and commit the new files in tests/api/.\n")
        assert False, "the committed tests/api/openapi.json is not what the app's API says"
    for name, sample in sorted(samples.items()):
        file = API / "samples" / name
        assert file.exists() and file.read_text(encoding="utf-8") == dump(sample), \
            f"tests/api/samples/{name} changed: run with --update-api and update the TUI to match"


def test_every_post_route_is_covered(generated):
    """A POST route nobody described is a route the TUI can't know: each one needs a sample body it can be sent, or a
    reason it must not be sent here."""
    _, samples, posts = generated
    requests = json.loads((API / "requests.json").read_text(encoding="utf-8"))
    excluded = json.loads((API / "excluded.json").read_text(encoding="utf-8"))
    for path in sorted(posts):
        assert path in requests or path in excluded, \
            f"{path} is in neither tests/api/requests.json nor tests/api/excluded.json: give it a sample body or a reason"
        assert not (path in requests and path in excluded), f"{path} is in both lists: exactly one"
    for path in sorted(set(requests) | set(excluded)):
        assert path in posts, f"{path} is listed in tests/api/ but is not a POST route of the app any more"
