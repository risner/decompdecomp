# decompdecomp's TUI: `decomp serve` in a terminal

`decomp serve` runs decompdecomp where there's no desktop to open a window on: the app itself (the server, the
agents, the autopilot) with a text front end in its terminal, and the full GUI paired to a browser through an SSH
tunnel. [The guide](GUIDE.md#on-a-server-decomp-serve) covers how you run it; this page says what the TUI shows, and — for anyone changing it, human
or agent — how it works inside.

## What you see

Three screens, switched with `1` `2` `3` (or `Tab`). The line at the top names the project and the browser address;
the line at the bottom lists the current screen's keys. `?` repeats them.

**1 · Projects.** One row per project: title, platform, a progress bar, matched over functions, the helpers working
on it now, and the progress error when a project can't be read. `Enter` opens the project's map.

**2 · Map.** The same map the window draws: every function a cell, five rows of them, as wide as the terminal. The
colour says the status —

| Colour | Status | Means |
| --- | --- | --- |
| pale green | polished | matched, and rewritten readable |
| green | matched | rebuilt byte for byte |
| yellow | in progress | an agent is working on it now |
| grey | tried | agents tried; no match yet |
| red | not C | no C makes it (set aside) |
| near white | open | nobody tried |

— and a cell of many functions (a big game packs several into one) shows the status most of them hold. The line
under the map describes the cell under the cursor; below that sit the project's numbers and a legend with counts.

`← ↓ ↑ →` and `h j k l` move; `Home`/`End` go to the row's ends, `g`/`G` to the first and last cell. `Enter` on a
cell of one function shows what the map knows about it; on a cell of several, a picker (type to filter) chooses
which. `/` searches names — results list as you type, `Enter` goes, `n` and `N` step through them.

**3 · Agents.** Who works on what now (agent, function, best score, tries, for how long); the day's board — each
agent's compiles and matches, with a sparkline of matches per hour over the last day; and the feed of attempts and
events as they happen, newest at the bottom, following until you scroll up (`f` follows again). `L` reads the tail
of `decomp.log`.

**Everywhere.** `b` shows a fresh one-time link for the browser; `r` refreshes now; `q` stops decompdecomp and its
agents — it asks first, because leaving the TUI stops the app. To leave it running, detach from `screen`
(`Ctrl-A d`) or `tmux` (`Ctrl-B d`) instead.

This first version only reads. Everything that changes a project — imports, settings, releases, notes, steering the
agents — is done in the browser (or the window). Function diffs, actions on functions and setup are on the roadmap
below.

## How it works inside

For changing the TUI, or changing the app's API without breaking it.

**It is one more client of the app's own HTTP API.** The TUI runs in the foreground of `decomp serve`, the server in
a background thread of the same process, and talks to it over HTTP on `127.0.0.1` carrying the per-launch secret in
its user agent — exactly like the window's JavaScript and `decomp`'s own commands. It sends only `GET`s: the
client (`tui/client.py`) has a `get()` and nothing else.

**The files** (`src/decompnet/app/tui/`):

| File | What's in it |
| --- | --- |
| `__init__.py` | `run()`: is there Textual and a TTY? Then the App; else `decomp serve` prints the address and link |
| `client.py` | `get()`: one GET, the secret in the user agent, `None` when the app isn't answering |
| `app.py` | the Textual App: the three screens, the everywhere-keys, the colours |
| `projects.py` | screen 1 |
| `mapview.py` | screen 2: the map, the picker, the info panel, search |
| `agents.py` | screen 3: working now, the board, the feed, the log |
| `mapgrid.py` | the map's layout and a cell's status — plain Python, no Textual |

**The layout** (`mapgrid.py`): the map is five lines by the terminal's width, `C` cells, functions in the API's
order (address, then unit). Fewer functions than cells: one each, the map shrinking to `ceil(n / width)` rows.
More functions than cells: cell `i` holds functions `floor(i × n / C)` to `floor((i + 1) × n / C) − 1`, every cell
full — 15,000 functions on 80 columns puts 37 or 38 in each. A function's status follows the window's `cellColor()`
(`static/js/map.js`): a claim first — work in progress shows over whatever is underneath — then matched (polished
apart), not C, tried, open. Claims and new attempts arrive with `/api/live` and are laid onto the map in place,
because the map's signature leaves them out on purpose (a game at work would re-send the whole map every second).
them out on purpose (a game at work would re-send the whole map every second).

**The colours** (`app.py`): the window's own, resolved once to the RGB a terminal takes — the CSS variables in
`static/app.css` can't be read at run time. Light and dark, as the terminal is; a text console (8 background
colours, `TERM=linux`) gets one basic colour per status instead of shades. The cursor is a `◆` (or `*`), black or
white over its cell, whichever contrasts.

**Keeping it in step with the API.** The project has many outside contributors, so an API change must not break the
TUI quietly, and fixing it must not fall on the maintainer. `tests/api/` holds a generated description of every `/api/`
route — field names in, field names and JSON types out, built by `tests/test_api_snapshot.py` on a project
seeded straight into the database — plus every answer, as it came, in `tests/api/samples/`. The TUI's own tests
answer from those samples. Change the API and the snapshot fails; regenerate it with `uv run pytest tests/test_api_snapshot.py --update-api`, update the TUI where it uses what changed, and commit both.
The rules for a pull request are in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Roadmap

In rough order: function detail (source, assembly, diffs); actions on functions (the keys `d` `v` `t` `x` `o` `p` `e` `R`
are kept free for them); steering the agents; setup as a workflow; text boxes with Tab completion wherever the
window opens a file chooser; import and restore; the compiler map's second colouring. The open question is
whether map cells should weigh functions by their instruction count instead of counting them equally.
