"""Tests for federation sheet merge (hub identity persistence)."""

from __future__ import annotations

import unittest

from hollow_grid.grid.local_hub import CharSheet
from hollow_grid.grid.sync import apply_hub_sheet
from hollow_grid.world.model import Player


class ApplyHubSheetTest(unittest.TestCase):
    def _player(self, faction: str = "ally") -> Player:
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

    def test_hub_none_does_not_clobber_ally(self) -> None:
        player = self._player("ally")
        apply_hub_sheet(player, CharSheet(faction="none"))
        self.assertEqual(player.faction, "ally")

    def test_hub_ally_applies(self) -> None:
        player = self._player("none")
        apply_hub_sheet(player, CharSheet(faction="ally"))
        self.assertEqual(player.faction, "ally")

    def test_hub_front_applies(self) -> None:
        player = self._player("none")
        apply_hub_sheet(player, CharSheet(faction="front"))
        self.assertEqual(player.faction, "front")


if __name__ == "__main__":
    unittest.main()
