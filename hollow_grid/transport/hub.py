"""Multiplayer presence registry (tell/yell routing lands in Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hollow_grid.world.model import Player


@dataclass
class Hub:
    """Session registry: who is in which room."""

    _by_name: dict[str, Player] = field(default_factory=dict)

    def register(self, player: Player) -> None:
        self._by_name[player.name] = player

    def unregister(self, name: str) -> None:
        self._by_name.pop(name, None)

    def sync(self, player: Player) -> None:
        self._by_name[player.name] = player

    def players_in_room(self, room_id: str, except_name: str = "") -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for player in self._by_name.values():
            if player.room_id != room_id or player.name == except_name:
                continue
            out.append({"name": player.name, "standing": _standing(player)})
        return out


def _standing(player: Player) -> str:
    if player.morality >= 25:
        return "virtuous"
    if player.morality <= -25 or player.faction == "Cinder Front":
        return "corrupt"
    return "neutral"
