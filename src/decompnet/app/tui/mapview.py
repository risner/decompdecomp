"""Screen 2: the function map (mapgrid.py lays it out), the line under it describing the cell under the cursor, the
project's overview numbers, and a legend; Enter on a cell of several functions opens a picker, `/` searches names.
Claims and new attempts arrive from /api/live and are laid onto the map in place, as the window does (its map
signature leaves them out on purpose: a map of a game at work would come again every second).
"""

from __future__ import annotations

import sys
import time

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from . import mapgrid
from .app import Base, palette, terminal_is_dark

FALLBACK_WIDTH = 80  # before the first layout, or when the terminal hasn't said
CURSOR = "◆" if "◆".encode(getattr(sys.stdout, "encoding", "") or "ascii", "ignore") else "*"  # a console without it


NAMED = {"black": 0.0, "blue": 0.07, "magenta": 0.15, "red": 0.21, "green": 0.15, "cyan": 0.25,
         "yellow": 0.6, "white": 0.9}  # the text console's 8: bright enough to put a black or white diamond over


def luminance(color: str) -> float:
    """A cell background's brightness (0–1): the cursor is drawn black or white over it, whichever reads."""
    if not color.startswith("#"):
        return NAMED.get(color, 0.5)

    def lin(u: float) -> float:
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def map_text(map_cells: list[range], statuses: list[str], cursor: int, colors: dict, width: int) -> Text:
    """The map as Textual shows it: every cell a space with its status colour behind it, the cursor a diamond over
    its own cell (black or white, whichever contrasts; * where the terminal can't show the diamond)."""
    out = Text()
    for i, status in enumerate(statuses):
        if i and i % width == 0:
            out.append("\n")
        color = colors[status]
        if i == cursor:
            out.append(CURSOR, style=f"{'black' if luminance(color) > 0.4 else 'white'} on {color}")
        else:
            out.append(" ", style=f"on {color}")
    return out


def legend_text(statuses: list[str], colors: dict) -> Text:
    """One line: each status's colour and how many functions hold it."""
    out = Text(" ")
    for status in mapgrid.ORDER:
        n = statuses.count(status)
        if n:
            out.append("■ ", style=colors[status]).append(f"{n} {status}   ")
    return out


class Picker(ModalScreen):
    """Enter on a cell holding several functions: which of them. Typing filters the list."""

    BINDINGS = [("escape", "dismiss", "close"), ("up", "up", None), ("down", "down", None),
                ("j", "down", None), ("k", "up", None), ("enter", "choose", "open")]

    def __init__(self, functions: list[dict]):
        super().__init__()
        self.functions = functions
        self.shown = list(functions)

    @staticmethod
    def line(fn: dict) -> str:
        best = f" · best {fn['best']}" if fn.get("best") is not None else ""
        return f" {fn['name']} · {mapgrid.status_of(fn)} · {fn.get('insns', 0)} insns{best}"

    def repopulate(self) -> None:
        self.query_one(OptionList).clear_options()
        for fn in self.shown:
            self.query_one(OptionList).add_option(Option(self.line(fn), id=fn["name"]))
        if self.shown:
            self.query_one(OptionList).highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        needle = (event.value or "").casefold()
        self.shown = [fn for fn in self.functions if needle in fn["name"].casefold()]
        self.repopulate()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_choose()  # Enter in the filter is Enter on the highlighted function

    def action_up(self) -> None:
        list_ = self.query_one(OptionList)
        if list_.highlighted is not None and list_.highlighted > 0:
            list_.highlighted -= 1

    def action_down(self) -> None:
        list_ = self.query_one(OptionList)
        if list_.highlighted is not None and list_.highlighted < len(self.shown) - 1:
            list_.highlighted += 1

    def action_choose(self) -> None:
        picked = self.query_one(OptionList).highlighted
        self.dismiss(self.shown[picked]["name"] if picked is not None and self.shown else None)

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        yield Static("  the cell's functions — type to filter", id="picker-hint")
        yield Input(placeholder="filter")
        yield OptionList(*[Option(self.line(fn), id=fn["name"]) for fn in self.shown])
        yield Static("", id="picker-pad")


class InfoPanel(ModalScreen):
    """A function, as far as the map row already knows it (code and diffs are on the roadmap)."""

    BINDINGS = [("escape", "dismiss", "close"), ("enter", "dismiss", "close")]

    def __init__(self, fn: dict):
        super().__init__()
        self.fn = fn

    def compose(self) -> ComposeResult:
        fn = self.fn
        at = time.strftime("%Y-%m-%d %H:%M", time.localtime(fn["matched_at"])) if fn.get("matched_at") else "—"
        fields = [("name", fn["name"]), ("address", f"{fn.get('vram') or 0:x}" if fn.get("vram") else "—"),
                  ("unit", fn.get("unit") or "—"), ("size", f"{fn.get('size') or 0} bytes"),
                  ("instructions", fn.get("insns", 0)), ("status", mapgrid.status_of(fn)),
                  ("best score", fn.get("best") if fn.get("best") is not None else "—"),
                  ("attempts", fn.get("attempts", 0)), ("agent", fn.get("agent") or "—"),
                  ("matched by", fn.get("matched_by") or "—"), ("matched at", at)]
        yield Static("\n".join(f"  {k:<12} {v}" for k, v in fields), id="info")


class Search(ModalScreen):
    """`/`: function names, case-insensitive substring, listed as you type; Enter goes to one."""

    BINDINGS = [("escape", "dismiss", "close"), ("enter", "choose", "go")]

    def __init__(self, rows: list[dict]):
        super().__init__()
        self.rows = rows
        self.hits = list(rows)

    def on_input_changed(self, event: Input.Changed) -> None:
        needle = (event.value or "").casefold()
        self.hits = [fn for fn in self.rows if needle in fn["name"].casefold()][:50]
        list_ = self.query_one(OptionList)
        list_.clear_options()
        for fn in self.hits:
            list_.add_option(Option(f" {fn['name']} · {mapgrid.status_of(fn)}", id=fn["name"]))
        if self.hits:
            list_.highlighted = 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_choose()  # Enter in the search box goes to the highlighted hit

    def action_choose(self) -> None:
        picked = self.query_one(OptionList).highlighted
        self.dismiss((self.hits[picked]["name"], self.hits) if picked is not None else None)

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        yield Input(placeholder="function names")
        yield OptionList()


class MapScreen(Base):
    """The map of one project, its claims and attempts laid on as they happen."""

    BINDINGS = [("left", "cursor_left", None), ("right", "cursor_right", None), ("up", "cursor_up", None),
                ("down", "cursor_down", None), ("h", "cursor_left", None), ("l", "cursor_right", None),
                ("j", "cursor_down", None), ("k", "cursor_up", None),
                ("home", "row_start", None), ("end", "row_end", None), ("g", "first", None), ("G", "last", None),
                ("enter", "open", "the cell"), ("/", "search", "search"), ("n", "again(1)", None),
                ("N", "again(-1)", None)]

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.rows: list[dict] = []
        self.sig: str | None = None
        self.map_cells: list[range] = []
        self.statuses: list[str] = []
        self.cursor = 0
        self.selected: int | None = None  # the function the cursor is on, in its cell
        self.slug: str | None = None
        self.find: tuple[str, list[int], int] | None = None  # needle, hits (row numbers), where in them
        self.last_event = 0
        self.last_attempt = 0
        self.overview_line = ""

    def body(self) -> list:
        return [Static("", id="map", classes="maparea"), Static("", id="cell-line"),
                Static("", id="overview-line"), Static("", id="legend-line")]

    def on_mount(self) -> None:
        self.set_interval(1.5, self.poll_live)
        self.set_interval(5, self.poll_map)

    def on_screen_resume(self) -> None:
        if self.slug:  # shown again (a project was opened into it, or the user came back): the map is fresh
            self.refresh_now()

    def on_resize(self) -> None:
        self.relayout()  # the terminal's width is the map's width; the cursor stays on its function

    def refresh_now(self) -> None:
        if not self.is_mounted:
            return
        self.sig = None  # ask for the whole map again, not the "nothing changed" of a poll
        self.poll_map()
        self.poll_live()

    def open_project(self, slug: str) -> None:
        self.slug, self.rows, self.sig, self.find = slug, [], None, None
        self.selected = None
        self.refresh_now()  # nothing yet when this screen isn't shown: its own on_mount starts the first fetch

    # -- the two polls

    def poll_map(self) -> None:
        if self.slug is None:
            return
        data = self.client.get("/api/map", slug=self.slug, since=self.sig)
        if data is None:
            self.say("the app isn't answering (restarting?)")
        elif not data.get("same"):
            self.sig = data["sig"]
            keys = data["keys"]
            self.rows = [dict(zip(keys, row)) for row in data["rows"]]
            self.relayout()

    def poll_live(self) -> None:
        if self.slug is None:
            return
        data = self.client.get("/api/live", slug=self.slug, e=self.last_event, a=self.last_attempt)
        if not data:
            return
        by_name = {fn["name"]: fn for fn in self.rows}
        for claim in data.get("claims") or []:  # who works on what, now: laid onto the map in place
            if fn := by_name.get(claim["name"]):
                fn["agent"] = claim.get("agent")
        for at in data.get("attempts") or []:  # each try, without refetching the map
            if fn := by_name.get(at["function"]):
                fn["attempts"] = fn.get("attempts", 0) + 1
                if at.get("score") is not None and (fn.get("best") is None or at["score"] < fn["best"]):
                    fn["best"] = at["score"]
        if data.get("events"):
            self.last_event = data["events"][-1]["id"]
        if data.get("attempts"):
            self.last_attempt = data["attempts"][-1]["id"]
        if overview := data.get("overview"):
            working = len(data.get("claims") or [])
            self.overview_line = (f" {overview.get('functions', 0)} functions · {overview.get('matched', 0)} matched"
                                  f" · {overview.get('set_aside', 0)} set aside"
                                  + (f" · {working} at work" if working else ""))
            self.app.say_project(str(overview.get("title") or self.slug))
        self.relayout()

    # -- layout and drawing

    def relayout(self) -> None:
        if not self.rows:
            return
        width = self.query_one("#map").size.width or FALLBACK_WIDTH
        stay_on = self.selected if self.selected is not None else (
            self.map_cells[self.cursor].start if self.map_cells and self.cursor < len(self.map_cells) else 0)
        self.map_cells = mapgrid.cells(len(self.rows), width)
        self.statuses = [mapgrid.status_of(fn) for fn in self.rows]
        self.cursor = mapgrid.cell_of(self.map_cells, min(stay_on, len(self.rows) - 1))
        self.selected = self.map_cells[self.cursor].start
        self.draw()

    def draw(self) -> None:
        if not self.map_cells:
            return
        colors = palette(terminal_is_dark(self.app), self._color_system())
        width = max(1, self.query_one("#map").size.width or FALLBACK_WIDTH)
        self.query_one("#map", Static).update(map_text(self.map_cells, self.cell_statuses(), self.cursor, colors, width))
        self.query_one("#cell-line", Static).update(self.describe())
        self.query_one("#overview-line", Static).update(self.overview_line)
        self.query_one("#legend-line", Static).update(legend_text(self.statuses, colors))

    def cell_statuses(self) -> list[str]:
        return [mapgrid.cell_status([self.statuses[i] for i in held]) for held in self.map_cells]

    def describe(self) -> str:
        """The line under the map: the cell under the cursor — one function, or the run a full cell holds."""
        held = self.map_cells[self.cursor]
        fns = [self.rows[i] for i in held]
        chosen = self.rows[self.selected] if self.selected is not None else fns[0]
        if len(fns) == 1:
            fn = fns[0]
            extra = []
            if fn.get("matched_by"):
                extra.append(f"matched by {fn['matched_by']}")
            elif fn.get("best") is not None:
                extra.append(f"best {fn['best']} of {fn.get('attempts', 0)} tries")
            return (f" cell {self.cursor} · {fn['name']} · {mapgrid.status_of(fn)} · {fn.get('insns', 0)} insns"
                    + (" · " + " · ".join(extra) if extra else ""))
        counts = {s: sum(1 for fn in fns if mapgrid.status_of(fn) == s) for s in mapgrid.ORDER}
        said = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
        return f" cell {self.cursor} · {len(fns)} functions · {fns[0]['name']} – {fns[-1]['name']} · {said} (on {chosen['name']})"

    def say(self, line: str) -> None:
        if self.is_mounted:
            self.query_one("#cell-line", Static).update(f" {line}")

    # -- keys

    def action_cursor_left(self) -> None:
        self.move_on_row(-1)

    def action_cursor_right(self) -> None:
        self.move_on_row(1)

    def action_cursor_up(self) -> None:
        self.move(-self.width())

    def action_cursor_down(self) -> None:
        self.move(self.width())

    def move(self, delta: int) -> None:
        """Up and down by a row: they stop at the map's top and bottom edges — the cursor stays where it is,
        rather than jumping to the map's first or last cell."""
        if self.map_cells and 0 <= self.cursor + delta < len(self.map_cells):
            self.cursor += delta
            self.selected = self.map_cells[self.cursor].start
            self.draw()

    def move_on_row(self, delta: int) -> None:
        """Left and right stop at the row's ends: they don't wrap onto the next row."""
        if self.map_cells:
            row, col = divmod(self.cursor, self.width())
            col = min(max(col + delta, 0), self.width() - 1)
            self.cursor = row * self.width() + col
            self.selected = self.map_cells[self.cursor].start
            self.draw()

    def action_row_start(self) -> None:
        self.cursor -= self.cursor % self.width()
        self.selected = self.map_cells[self.cursor].start
        self.draw()

    def action_row_end(self) -> None:
        row, _ = divmod(self.cursor, self.width())
        self.cursor = min((row + 1) * self.width() - 1, len(self.map_cells) - 1)
        self.selected = self.map_cells[self.cursor].start
        self.draw()

    def action_first(self) -> None:
        self.cursor, self.selected = 0, self.map_cells[0].start
        self.draw()

    def action_last(self) -> None:
        self.cursor = len(self.map_cells) - 1
        self.selected = self.map_cells[self.cursor].start
        self.draw()

    def width(self) -> int:
        return max(1, self.query_one("#map").size.width or FALLBACK_WIDTH)

    def action_open(self) -> None:
        if not self.map_cells:
            return
        held = self.map_cells[self.cursor]
        if len(held) == 1:
            self.app.push_screen(InfoPanel(self.rows[held.start]))
        else:
            self.app.push_screen(Picker([self.rows[i] for i in held]), self.picked)

    def picked(self, name: str | None) -> None:
        if name and (i := next((i for i, fn in enumerate(self.rows) if fn["name"] == name), None)) is not None:
            self.selected = i
            self.cursor = mapgrid.cell_of(self.map_cells, i)
            self.app.push_screen(InfoPanel(self.rows[i]))

    def action_search(self) -> None:
        if self.rows:
            self.app.push_screen(Search(self.rows), self.searched)

    def searched(self, found: tuple[str, list[dict]] | None) -> None:
        if not found:
            return
        needle, hits = found
        indices = [i for i, fn in enumerate(self.rows) if fn["name"] in {h["name"] for h in hits}]
        self.find = (needle, indices, -1)
        self.action_again(1)

    def action_again(self, direction: int) -> None:
        if not self.find or not self.find[1]:
            self.say("nothing found yet — / searches names")
            return
        needle, hits, at = self.find
        at = (at + direction) % len(hits)
        self.find = (needle, hits, at)
        self.selected = hits[at]
        self.cursor = mapgrid.cell_of(self.map_cells, hits[at])
        self.say(f" {hits[at] + 1}/{len(hits)} · {self.rows[hits[at]]['name']}")
        self.draw()

    def _color_system(self) -> str:
        return getattr(self.app._driver, "color_system", "") if self.app._driver else ""
