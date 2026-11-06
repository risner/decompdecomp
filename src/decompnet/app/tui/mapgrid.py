"""The map's layout and a cell's status: plain functions of (functions, width), no Textual (tests/test_tui_mapgrid.py),
so the TUI's one interesting decision — which functions share a character cell, and what that cell shows — is decided
and checked without a terminal.

The map is ROWS lines high and as wide as the terminal, C = ROWS × width cells, functions in the API's order (address,
then unit). Fewer functions than cells: one per cell, the map shrinking to ceil(n / width) rows. More functions than
cells: cell i holds functions floor(i × n / C) to floor((i + 1) × n / C) − 1, every cell full (mapview.py draws it).

A function's status follows the window's cellColor (static/js/map.js): a claim comes first — work in progress shows
whatever is underneath it — then matched (polished apart), not C, tried, open. The window's map rows come from
/api/map, whose own `status` field already says "working" for a claim the map was built after; claims that arrived
since (in /api/live) are laid onto the rows by the caller before status_of sees them, as the window does.
"""

from __future__ import annotations

from collections import Counter

ROWS = 5
# a cell's status when several tie for most: work done first, work happening now before what it happens to
ORDER = ("polished", "matched", "in progress", "tried", "not C", "open")


def status_of(row) -> str:
    """One function's status from its /api/map row: polished, matched, in progress, not C, tried or open."""
    if row.get("status") == "matched":
        return "polished" if row.get("polished") else "matched"
    if row.get("status") == "working" or row.get("agent"):
        return "in progress"
    if row.get("status") == "asm":
        return "not C"
    return "tried" if row.get("best") is not None else "open"


def cells(n: int, width: int) -> list[range]:
    """Which functions each cell holds, in the API's order: one each when they fit (the map shrinks to match), runs
    of neighbouring functions when they don't (every cell full)."""
    if n <= 0:
        return []
    if n <= ROWS * width:
        return [range(i, i + 1) for i in range(n)]
    c = ROWS * width
    return [range(i * n // c, (i + 1) * n // c) for i in range(c)]


def rows_used(n: int, width: int) -> int:
    """How many lines the map fills (as many as it has cells for; a wide terminal with few functions shows one)."""
    return (len(cells(n, width)) + width - 1) // width


def cell_status(statuses) -> str:
    """What a cell shows: the status most of its functions hold, ties going to the first in ORDER."""
    counts = Counter(statuses)
    return max(counts, key=lambda s: (counts[s], -ORDER.index(s)))


def cell_of(layout: list[range], function: int) -> int:
    """The cell holding function `function` — where the cursor goes after a search, or a resize (the cursor stays on
    its function; which cell that is may change)."""
    for i, held in enumerate(layout):
        if function in held:
            return i
    return 0
