"""Public standing tags others see on a player."""

from __future__ import annotations

from hollow_grid.world.model import Player


def brand(player: Player) -> str:
    if player.ashsworn:
        return "ash-sworn"
    if player.faction in {"front", "Cinder Front"}:
        return "Cinder Front"
    if player.faction == "ally":
        return "Free Folk ally"
    if player.morality >= 50:
        return "a beacon of the wastes"
    if player.morality <= -50:
        return "reviled"
    return ""
