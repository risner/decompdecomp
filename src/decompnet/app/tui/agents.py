"""Screen 3: the agents — who works on what now (the claims /api/live brings), the board (/api/stats: compiles,
matches, a sparkline of matches per hour over the last day), and the feed of attempts and events, newest at the
bottom and following until you scroll up (`f`). `L` reads the tail of decomp.log (on request only: it can be big).
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.screen import ModalScreen
from textual.widgets import DataTable, RichLog, Static

from .app import Base

LIVE_POLL, STATS_POLL, EVENTS_POLL = 2, 10, 5
SPARK = "▁▂▃▄▅▆▇█"  # a sparkline's heights, low to high
FEED_LINES = 500  # the feed keeps this many; a terminal shows far fewer


def sparkline(per_hour: list) -> str:
    """24 hours of matches as one line of block characters (the window draws the same numbers as a chart)."""
    top = max(per_hour or [1])
    return "".join(SPARK[min(len(SPARK) - 1, v * len(SPARK) // (top or 1))] for v in (per_hour or []))


def how_long(claimed_at) -> str:
    """How long a claim has run ("14 m", "2 h 05"); "—" for one with no time (a room's claim)."""
    if not claimed_at:
        return "—"
    minutes = max(0, int((time.time() - claimed_at) / 60))
    return f"{minutes // 60} h {minutes % 60:02d} m" if minutes >= 60 else f"{minutes} m"


class LogView(ModalScreen):
    """`L`: the end of decomp.log, scrollable (the whole log is in the file; this is its last 512 KB)."""

    BINDINGS = [("escape", "dismiss", "close"), ("L", "dismiss", "close"), ("l", "dismiss", "close")]

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def action_dismiss(self) -> None:
        self.dismiss()

    def compose(self):
        yield Static(self.text or "(nothing logged yet)", id="logview")


class AgentsScreen(Base):
    """The helpers at work: now, over the day, and as it happens."""

    BINDINGS = [("f", "follow", "follow the feed"), ("L", "log", "the log")]

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.follow = True
        self.slug: str | None = None
        self.last_event = 0
        self.last_attempt = 0
        self.last_note = 0

    def body(self) -> list:
        working = DataTable(id="working", cursor_type="row", zebra_stripes=True)
        working.add_columns("agent", "function", "best", "tries", "for")
        board = DataTable(id="board", cursor_type="row", zebra_stripes=True)
        board.add_columns("agent", "compiles", "matches", "per hour (24 h)")
        return [Static(" working now", classes="heading"), working, Static(" the day", classes="heading"), board,
                Static(" the feed  (f follows, or stops at what you're reading)", classes="heading"),
                RichLog(id="feed", markup=False, wrap=True)]

    def on_mount(self) -> None:
        self.set_interval(LIVE_POLL, self.poll_live)
        self.set_interval(STATS_POLL, self.poll_stats)
        self.set_interval(EVENTS_POLL, self.poll_events)

    def refresh_now(self) -> None:
        self.slug = getattr(self.app.screens.get("map"), "slug", None)
        self.poll_live()
        self.poll_stats()
        self.poll_events()

    # -- the three polls

    def poll_live(self) -> None:
        slug = getattr(self.app.screens.get("map"), "slug", None)
        if slug is None:
            return
        self.slug = slug
        data = self.client.get("/api/live", slug=slug, e=self.last_event, a=self.last_attempt)
        if not data:
            return
        table = self.query_one("#working", DataTable)
        on = table.cursor_row if table.row_count else 0
        table.clear()
        for c in data.get("claims") or []:
            best = "—" if c.get("best_score") is None else str(c["best_score"])
            table.add_row(str(c.get("agent") or "?"), str(c["name"]), best, str(c.get("attempts", 0)),
                          how_long(c.get("claimed_at")))
        if table.row_count:
            table.move_cursor(row=min(on, table.row_count - 1), animate=False)
        for at in data.get("attempts") or []:
            score = "didn't compile" if not at.get("compiled") else f"score {at['score']}"
            self.feeds(f" {at.get('agent') or '?'} tried {at['function']} · {score}")
        for event in data.get("events") or []:
            self.feeds(f" {event['kind']}: {event['detail']}")
        if data.get("attempts"):
            self.last_attempt = data["attempts"][-1]["id"]
        if data.get("events"):
            self.last_event = data["events"][-1]["id"]

    def poll_stats(self) -> None:
        if self.slug is None:
            return
        stats = self.client.get("/api/stats", slug=self.slug)
        if not stats:
            return
        table = self.query_one("#board", DataTable)
        on = table.cursor_row if table.row_count else 0
        table.clear()
        for row in stats.get("agents") or []:
            table.add_row(str(row.get("agent") or "?"), str(row.get("compiles", 0)), str(row.get("matched", 0)),
                          Text(sparkline(stats.get("matches_per_hour"))))
        if table.row_count:
            table.move_cursor(row=min(on, table.row_count - 1), animate=False)

    def poll_events(self) -> None:
        """The notification centre's feed, across every project (as the window's bell shows it)."""
        data = self.client.get("/api/events", after=self.last_note)
        if not data or not data.get("events"):
            return
        for event in data["events"]:
            self.feeds(f" · {event['kind']}: {event['detail']}")
        self.last_note = data["events"][-1]["id"]

    def feeds(self, line: str) -> None:
        feed = self.query_one("#feed", RichLog)
        feed.write(line, shrink=True)
        if self.follow:
            feed.scroll_end(animate=False)

    # -- keys

    def action_follow(self) -> None:
        self.follow = not self.follow
        if self.follow:
            self.query_one("#feed", RichLog).scroll_end(animate=False)

    def action_log(self) -> None:
        self.app.push_screen(LogView(str(self.client.get("/api/log") or "")))
