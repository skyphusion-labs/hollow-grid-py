"""Tests for federation sheet merge and hub identity commit."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any

from hollow_grid.grid.local_hub import CharSheet
from hollow_grid.grid.remote import GridHubError
from hollow_grid.grid.async_rpc import grid_rpc
from hollow_grid.grid.sync import apply_hub_sheet, commit_hub_async, merge_hub_on_login_async
from hollow_grid.world.model import Player


@dataclass
class FakeServer:
    grid: FakeRemoteGrid
    world: Any = None
    grid_hub_detached: bool = False

    def __post_init__(self) -> None:
        if self.world is None:
            from types import SimpleNamespace

            self.world = SimpleNamespace(name="Verdigris Spool", url="ws://127.0.0.1:8791/ws")


@dataclass
class FakeRemoteGrid:
    """In-memory remote hub for federation commit/load tests."""

    sheets: dict[str, CharSheet] = field(default_factory=dict)
    fail_commits: int = 0
    _commit_calls: int = 0
    registered: list[tuple[str, str]] = field(default_factory=list)

    def remote(self) -> bool:
        return True

    def load_character(self, name: str) -> tuple[CharSheet, bool]:
        sheet = self.sheets.get(name, CharSheet())
        found = name in self.sheets
        return sheet, found

    def commit_character(self, name: str, sheet: CharSheet) -> None:
        self._commit_calls += 1
        if self.fail_commits > 0:
            self.fail_commits -= 1
            raise GridHubError("commitCharacter: simulated failure")
        self.sheets[name] = sheet

    def register(self, world: str, url: str) -> None:
        self.registered.append((world, url))


def _player(faction: str = "none") -> Player:
    return Player(
        name="Tester",
        race="human",
        room_id="nexus",
        faction=faction,
        morality=10,
        title="",
        level=1,
        xp=0,
        gold=0,
        hp=30,
        max_hp=30,
    )


def _server(grid: FakeRemoteGrid) -> FakeServer:
    return FakeServer(grid=grid)


class ApplyHubSheetTest(unittest.TestCase):
    def test_hub_none_applies_over_local_ally(self) -> None:
        """Remote redemption on another world: hub 'none' is authoritative."""
        player = _player("ally")
        apply_hub_sheet(player, CharSheet(faction="none"))
        self.assertEqual(player.faction, "none")

    def test_hub_ally_applies(self) -> None:
        player = _player("none")
        apply_hub_sheet(player, CharSheet(faction="ally"))
        self.assertEqual(player.faction, "ally")

    def test_hub_front_applies(self) -> None:
        player = _player("none")
        apply_hub_sheet(player, CharSheet(faction="front"))
        self.assertEqual(player.faction, "front")


class CommitHubAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_standing_change_lands_on_hub_before_relogin(self) -> None:
        grid = FakeRemoteGrid()
        server = _server(grid)
        player = _player("none")
        player.faction = "ally"

        ok = await commit_hub_async(server, player)
        self.assertTrue(ok)
        self.assertFalse(server.grid_hub_detached)

        relog = _player("none")
        canon, _ = await grid_rpc(grid, grid.load_character, relog.name)
        apply_hub_sheet(relog, canon)
        self.assertEqual(relog.faction, "ally")

    async def test_commit_retries_once_then_succeeds(self) -> None:
        grid = FakeRemoteGrid(fail_commits=1)
        server = _server(grid)
        player = _player("ally")

        ok = await commit_hub_async(server, player)
        self.assertTrue(ok)
        self.assertEqual(grid._commit_calls, 2)
        self.assertFalse(server.grid_hub_detached)

    async def test_commit_failure_marks_detached(self) -> None:
        grid = FakeRemoteGrid(fail_commits=2)
        server = _server(grid)
        player = _player("ally")

        ok = await commit_hub_async(server, player)
        self.assertFalse(ok)
        self.assertTrue(server.grid_hub_detached)

    async def test_grid_rpc_skips_thread_for_local_hub(self) -> None:
        class LocalOnly:
            def remote(self) -> bool:
                return False

            def ping(self) -> str:
                return "ok"

        grid = LocalOnly()
        self.assertEqual(await grid_rpc(grid, grid.ping), "ok")  # type: ignore[arg-type]


class MergeHubOnLoginAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_merge_applies_canonical_sheet(self) -> None:
        grid = FakeRemoteGrid(sheets={"Tester": CharSheet(faction="ally", race="elf")})
        server = _server(grid)
        player = _player("none")

        await merge_hub_on_login_async(server, player)

        self.assertEqual(player.faction, "ally")
        self.assertEqual(player.race, "elf")

    async def test_merge_registers_world_on_login(self) -> None:
        grid = FakeRemoteGrid()
        server = _server(grid)
        player = _player("none")

        await merge_hub_on_login_async(server, player)

        self.assertEqual(grid.registered, [("Verdigris Spool", "ws://127.0.0.1:8791/ws")])


if __name__ == "__main__":
    unittest.main()
