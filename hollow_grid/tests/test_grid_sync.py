"""Tests for federation sheet merge and hub identity commit."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any

from hollow_grid.grid.local_hub import CharSheet
from hollow_grid.grid.remote import GridHubError
from hollow_grid.grid.sync import apply_hub_sheet, commit_hub
from hollow_grid.world.model import Player


@dataclass
class FakeServer:
    grid: FakeRemoteGrid
    grid_hub_detached: bool = False


@dataclass
class FakeRemoteGrid:
    """In-memory remote hub for federation commit/load tests."""

    sheets: dict[str, CharSheet] = field(default_factory=dict)
    fail_commits: int = 0
    _commit_calls: int = 0

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
        _ = (world, url)


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


class CommitHubTest(unittest.TestCase):
    def test_standing_change_lands_on_hub_before_relogin(self) -> None:
        grid = FakeRemoteGrid()
        server = _server(grid)
        player = _player("none")
        player.faction = "ally"

        ok = commit_hub(server, player)
        self.assertTrue(ok)
        self.assertFalse(server.grid_hub_detached)

        relog = _player("none")
        canon, _ = grid.load_character(relog.name)
        apply_hub_sheet(relog, canon)
        self.assertEqual(relog.faction, "ally")

    def test_commit_retries_once_then_succeeds(self) -> None:
        grid = FakeRemoteGrid(fail_commits=1)
        server = _server(grid)
        player = _player("ally")

        ok = commit_hub(server, player)
        self.assertTrue(ok)
        self.assertEqual(grid._commit_calls, 2)
        self.assertFalse(server.grid_hub_detached)

    def test_commit_failure_marks_detached(self) -> None:
        grid = FakeRemoteGrid(fail_commits=2)
        server = _server(grid)
        player = _player("ally")

        ok = commit_hub(server, player)
        self.assertFalse(ok)
        self.assertTrue(server.grid_hub_detached)


if __name__ == "__main__":
    unittest.main()
