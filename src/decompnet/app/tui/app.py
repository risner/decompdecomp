"""The Textual App: the three screens (projects.py, mapview.py, agents.py), the keys that work everywhere, and the
colours. It holds one Client of the app it runs beside (cli.py started both) and decomp serve's one-time links
(sessions.py): `b` shows a fresh one for the browser.
"""

from __future__ import annotations

import os

from textual.app import App
from textual.binding import Binding
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Footer, Static

# The window's map colours (static/app.css, over tokens.css), resolved once to the RGB a terminal takes: the TUI
# can't read CSS variables at run time, so each value names where it came from. Light and dark, picked by the
# terminal Textual sees; the text console (8 background colours) gets one basic colour per status instead of shades.
DARK = {  # the dark theme: todo is the text colour, near-white, the strongest contrast on a dark screen
    "polished": "#90bf95",     # color-mix(oklch, success-fill 50%, text-primary)
    "matched": "#1b9247",      # --color-status-success-fill
    "in progress": "#f2cf24",  # --color-mark-fill
    "tried": "#3f3e38",        # color-mix(oklch, border-strong 55%, surface-base)
    "not C": "#d73337",        # --color-status-danger-fill
    "open": "#edebe5",         # --todo = --ink = --color-text-primary
}
LIGHT = {  # the light theme: todo is near-black, tried a light grey
    "polished": "#26502a",
    "matched": "#1b9247",
    "in progress": "#ffdc2f",
    "tried": "#bab9b2",
    "not C": "#d73337",
    "open": "#18160f",
}
CONSOLE = {"polished": "cyan", "matched": "green", "in progress": "yellow", "tried": "red",
           "not C": "magenta", "open": "blue"}  # TERM=linux and friends: 8 background colours, no shades


def palette(dark: bool, color_system: str) -> dict[str, str]:
    """A colour per map status for this terminal: the window's own (light or dark as the terminal is) where it takes
    256 or true colour, the console's one-basic-colour-per-status where it takes 8 or 16."""
    if color_system in ("", "mono", "8", "16") and "256color" not in os.environ.get("TERM", "") \
            and os.environ.get("COLORTERM", "") == "":
        return CONSOLE
    return DARK if dark else LIGHT


def terminal_is_dark(app: App) -> bool:
    """Whether the theme Textual picked is a dark one (a dark terminal gets the dark-theme map colours, a light one
    the window's light set)."""
    theme = getattr(app, "theme", None)
    return True if theme is None else bool(getattr(theme, "dark", True))


class TopBar(Static):
    """The one line above everything: the project the map is on, and where a browser reaches the same app."""

    def on_mount(self) -> None:
        self.show()

    def show(self) -> None:
        app: DecompApp = self.app
        self.update(f" {app.project_name or 'no project open yet'} · browser (through the tunnel): {app.browser_address}")


class Base(Screen):
    """Every screen's frame: the top bar, the screen's own body, the keys (Textual's Footer, from the bindings)."""

    def compose(self):
        yield TopBar()
        yield from self.body()
        yield Footer()

    def body(self) -> list[Widget]:
        return [Static("")]


class AskStop(ModalScreen):
    """`q`, and Ctrl-C: leaving the TUI ends the app and every helper with it (cli.run's quit_app), so it asks."""

    BINDINGS = [("escape", "dismiss", "leave it"), ("n", "dismiss", "leave it"),
                ("y", "stop", "stop everything"), ("enter", "stop", "stop everything")]

    def action_stop(self) -> None:
        self.app.exit()

    def action_dismiss(self) -> None:
        self.dismiss()

    def compose(self):
        yield Static("  Stop decompdecomp and its agents?\n\n"
                     "  y stops everything; n leaves it running\n"
                     "  (leave it running and close the TUI instead: detach from screen or tmux,\n"
                     "   Ctrl-A d / Ctrl-B d)", id="ask")
        yield Footer()


class BrowserLink(ModalScreen):
    """`b`: a fresh one-time link for the browser, from decomp serve itself (sessions.py)."""

    BINDINGS = [("escape", "dismiss", "close"), ("b", "link", "a fresh one"), ("enter", "dismiss", "close")]

    def action_dismiss(self) -> None:
        self.dismiss()

    def action_link(self) -> None:
        self.query_one("#link", Static).update(f"  {self.app.fresh_link()}")

    def compose(self):
        yield Static(f"  {self.app.fresh_link()}\n\n  open it in the browser through the SSH tunnel; it works once",
                     id="link")
        yield Footer()


class ShowKeys(ModalScreen):
    BINDINGS = [("escape", "dismiss", "close"), ("?", "dismiss", "close")]

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def action_dismiss(self) -> None:
        self.dismiss()

    def compose(self):
        yield Static(self.text, id="keys")
        yield Footer()


HELP = "\n".join([
    "  everywhere   1 2 3 screens · Tab next · b browser link · r refresh · q stop · ? this list",
    "  projects     Enter opens the project's map",
    "  map          ← ↓ ↑ → h j k l move · Home End the row · g G first/last cell · Enter the cell's function(s)",
    "               / search · n N next and previous find",
    "  agents       f follow the feed on and off · L the log's tail",
])


class DecompApp(App):
    """decompdecomp in a terminal: read-only in this first version."""

    TITLE = "decompdecomp"
    CSS = """
    TopBar { background: $panel; color: $text; height: 1; text-style: bold; }
    #ask, #link, #keys, #info, #picker-hint, #logview { padding: 1 2; border: round $primary; }
    #ask, #link, #keys, #info { width: auto; height: auto; }
    .heading { color: $text-muted; text-style: bold; height: 1; }
    .maparea { height: 5; overflow: hidden; }  /* the map: five lines, as wide as the terminal */
    #cell-line { height: 1; color: $text; }
    #overview-line, #legend-line { height: 1; color: $text-muted; }
    #working { height: 5; } #board { height: 6; } #feed { border: round $primary; }
    #logview { height: 1fr; width: 1fr; overflow-y: auto; }
    """
    BINDINGS = [
        ("1", "screen('projects')", "Projects"),
        ("2", "screen('map')", "Map"),
        ("3", "screen('agents')", "Agents"),
        Binding("tab", "next_screen", "next", priority=True),  # Tab walks the screens, not the widgets
        ("b", "link", "browser link"),
        ("r", "refresh", "refresh"),
        ("q", "ask", "stop"),
        ("ctrl+c", "ask", "stop"),
        ("?", "keys", "keys"),
    ]
    ORDER = ("projects", "map", "agents")  # what Tab walks through

    def __init__(self, client, new_code):
        super().__init__()
        self.client = client
        self.new_code = new_code
        self.project_name = ""
        self.browser_address = client.base
        self.screens: dict[str, Base] = {}

    def fresh_link(self) -> str:
        return f"{self.client.base}/pair?code={self.new_code()}"

    def on_mount(self) -> None:
        from . import agents, mapview, projects  # at run time: they import this module for Base and the palette

        self.screens = {"projects": projects.ProjectsScreen(self.client),
                        "map": mapview.MapScreen(self.client),
                        "agents": agents.AgentsScreen(self.client)}
        for name, screen in self.screens.items():
            self.install_screen(screen, name=name)
        self.push_screen("projects")  # pushed, not switched: the startup screen has no callback to switch away from

    def say_project(self, name: str) -> None:
        """The top bar names the project the map is on (mapview, when a map arrives)."""
        self.project_name = name
        for screen in self.screen_stack:
            if isinstance(screen, Base):
                found = screen.query(TopBar)
                if len(found):
                    found[0].show()

    def action_screen(self, name: str) -> None:
        self.switch_screen(name)

    def action_next_screen(self) -> None:
        current = next((name for name in self.ORDER if self.screens.get(name) is self.screen), self.ORDER[0])
        self.switch_screen(self.ORDER[(self.ORDER.index(current) + 1) % len(self.ORDER)])

    def action_link(self) -> None:
        self.push_screen(BrowserLink())

    def action_ask(self) -> None:
        self.push_screen(AskStop())

    def action_keys(self) -> None:
        self.push_screen(ShowKeys(HELP))

    def action_refresh(self) -> None:
        for screen in self.screens.values():
            screen.refresh_now()
