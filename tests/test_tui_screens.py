"""The TUI's screens, driven with Textual's pilot (App.run_test) against a fake client that answers from
tests/api/samples/ — the real answers the API snapshot saved. An answer that changes shape breaks the snapshot first
(tests/test_api_snapshot.py) and the screens here second: the TUI can't drift from the app quietly.
"""

import json
from pathlib import Path

import pytest

from decompnet.app.tui.app import DecompApp

SAMPLES = Path(__file__).parent / "api" / "samples"


class FakeClient:
    """Answers as the app did when tests/api/ was generated. `functions`: the map sample tiled up to that many
    functions, so a picker or a search has cells of several to work on."""

    def __init__(self, functions: int = 0):
        self.base = "http://127.0.0.1:6499"
        self.functions = functions

    def get(self, path: str, **params):
        sample = json.loads((SAMPLES / (path.lstrip("/").replace("/", "_") + ".json")).read_text(encoding="utf-8"))
        if path == "/api/map":
            if self.functions > len(sample["rows"]):
                base = sample["rows"]
                rows = [list(base[i % len(base)]) for i in range(self.functions)]
                at = list(sample["keys"]).index("name")
                for i, row in enumerate(rows):  # neighbouring functions keep their own names, as a game's do
                    row[at] = f"func_{0x80000000 + i * 0x10:08X}"
                sample = sample | {"rows": rows}
            if params.get("since") == sample["sig"]:
                return sample["unchanged"]  # the poll when nothing changed
        return sample


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def make(functions: int = 0):
    """The app on the samples, with its pilot: `async with (await make()) as pilot:`."""
    app = DecompApp(FakeClient(functions), lambda: "a-fresh-code")
    return app.run_test(size=(100, 30))


@pytest.mark.anyio
async def test_the_three_screens_switch():
    async with (await make()) as pilot:
        app = pilot.app
        assert type(app.screen).__name__ == "ProjectsScreen"
        await pilot.press("2")
        assert type(app.screen).__name__ == "MapScreen"
        await pilot.press("3")
        assert type(app.screen).__name__ == "AgentsScreen"
        await pilot.press("tab")  # tab walks the same round
        assert type(app.screen).__name__ == "ProjectsScreen"
        await pilot.press("1")  # a number goes straight there
        assert type(app.screen).__name__ == "ProjectsScreen"
        await pilot.press("3")
        assert type(app.screen).__name__ == "AgentsScreen"


@pytest.mark.anyio
async def test_projects_open_the_map():
    async with (await make()) as pilot:
        app = pilot.app
        table = app.screen.query_one("#projects")
        await pilot.pause()
        assert table.row_count == 2  # the seeded projects, as the sample lists them
        await pilot.press("down", "enter")  # the readable one is the second row
        assert type(app.screen).__name__ == "MapScreen"
        await pilot.pause()
        assert app.screens["map"].slug == "tui-seed"
        assert len(app.screens["map"].rows) == 8
        assert app.project_name == "TUI Seed"  # the top bar names it


@pytest.mark.anyio
async def test_moving_on_the_map_with_arrows_and_vi_keys():
    async with (await make()) as pilot:
        app = pilot.app
        await pilot.press("2")
        await pilot.pause()
        map_screen = app.screens["map"]
        map_screen.open_project("tui-seed")
        await pilot.pause()
        assert map_screen.cursor == 0
        await pilot.press("right", "right", "left")
        assert map_screen.cursor == 1
        await pilot.press("l", "l", "h")
        assert map_screen.cursor == 2
        await pilot.press("down", "up")  # one row of eight: up and down stop at its edges
        assert map_screen.cursor == 2
        await pilot.press("end")
        assert map_screen.cursor == 7  # the row's last cell
        await pilot.press("home")
        assert map_screen.cursor == 0
        await pilot.press("G", "g")
        assert map_screen.cursor == 0
        said = app.screens["map"].describe()
        assert "func_80000000" in said and "polished" in said


@pytest.mark.anyio
async def test_the_picker_for_a_cell_of_several_functions():
    async with (await make(functions=1000)) as pilot:  # 1000 functions, 100 columns: five to a cell
        app = pilot.app
        await pilot.press("2")
        map_screen = app.screens["map"]
        map_screen.open_project("tui-seed")
        await pilot.pause()
        assert len(map_screen.map_cells[0]) > 1  # cells share functions, as a big game's do
        await pilot.press("enter")
        assert type(app.screen).__name__ == "Picker"
        await pilot.pause()
        await pilot.press(*"func_80000")  # typing filters the picker
        await pilot.pause()
        await pilot.press("enter")  # the highlighted one's info
        assert type(app.screen).__name__ == "InfoPanel"
        await pilot.press("escape")
        assert app.screen is map_screen


@pytest.mark.anyio
async def test_search_with_n_and_n():
    async with (await make(functions=1000)) as pilot:
        app = pilot.app
        await pilot.press("2")
        map_screen = app.screens["map"]
        map_screen.open_project("tui-seed")
        await pilot.pause()
        await pilot.press("/")
        assert type(app.screen).__name__ == "Search"
        await pilot.press(*"FUNC_8000")  # case doesn't matter
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert map_screen.find is not None and map_screen.find[2] == 0  # on the first hit
        first = map_screen.selected
        await pilot.press("n")
        assert map_screen.selected != first and map_screen.find[2] == 1
        await pilot.press("N")
        assert map_screen.selected == first and map_screen.find[2] == 0


@pytest.mark.anyio
async def test_b_shows_a_one_time_browser_link():
    async with (await make()) as pilot:
        await pilot.press("b")
        assert type(pilot.app.screen).__name__ == "BrowserLink"
        text = pilot.app.screen.query_one("#link").content
        assert "/pair?code=a-fresh-code" in str(text)
        await pilot.press("b")  # b again, inside it: a fresh one, shown at once
        assert "/pair?code=a-fresh-code" in str(pilot.app.screen.query_one("#link").content)
        await pilot.press("escape")


@pytest.mark.anyio
async def test_q_asks_before_it_stops_everything():
    async with (await make()) as pilot:
        app = pilot.app
        await pilot.press("q")
        assert type(app.screen).__name__ == "AskStop"
        await pilot.press("n")  # leave it running: the TUI stays
        assert type(app.screen).__name__ == "ProjectsScreen"
        assert app.is_running
        await pilot.press("q", "y")  # stop: the app ends (decomp serve then quits with it)
        await pilot.pause()
        assert not app.is_running
