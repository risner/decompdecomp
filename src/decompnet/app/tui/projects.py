"""Screen 1: the projects, one row each — title, platform, a progress bar, matched over functions, the helpers
working on it now, and the progress error when a project can't be read (/api/projects, every 5 s). Enter opens the
project's map."""

from __future__ import annotations

from textual.binding import Binding
from textual.widgets import DataTable

from .app import Base

POLL = 5


def progress_bar(matched: int, functions: int, width: int = 10) -> str:
    """How far the project got, as text: a bar and its share of functions matched."""
    share = matched / functions if functions else 0.0
    filled = round(share * width)
    return f"{'█' * filled}{'░' * (width - filled)} {share:.0%}"


class ProjectsScreen(Base):
    """Every project, as the sidebar shows them (the home page of the TUI)."""

    BINDINGS = [Binding("enter", "open", "open the map", priority=True)]  # over the table's own Enter

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.projects: list[dict] = []

    def body(self) -> list:
        table = DataTable(id="projects", cursor_type="row", zebra_stripes=True)
        table.add_columns("project", "platform", "progress", "matched", "helpers", "notes")
        return [table]

    def on_mount(self) -> None:
        self.set_interval(POLL, self.poll)
        self.poll()

    def refresh_now(self) -> None:
        self.poll()

    def poll(self) -> None:
        projects = self.client.get("/api/projects")
        if not isinstance(projects, list):
            return  # nothing yet (the app is starting, or restarting): the last list stays
        self.projects = projects
        table = self.query_one(DataTable)
        on = table.cursor_row if table.row_count else 0
        table.clear()
        for p in projects:
            note = p.get("progress_error") or p.get("broken") or ""
            table.add_row(str(p.get("title") or p["slug"]), str(p.get("platform_short") or "?"),
                          progress_bar(int(p.get("matched") or 0), int(p.get("functions") or 0)),
                          f"{p.get('matched', 0)}/{p.get('functions', 0)}", str(p.get("working", 0)),
                          str(note)[:60])
        if table.row_count:
            table.move_cursor(row=min(on, table.row_count - 1), animate=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """The table's own Enter (its binding outranks the screen's): a selected row opens like action_open."""
        self.action_open()

    def action_open(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row < len(self.projects):
            self.app.switch_screen("map")  # shown first: its widgets exist only once it is
            self.app.screens["map"].open_project(self.projects[table.cursor_row]["slug"])
