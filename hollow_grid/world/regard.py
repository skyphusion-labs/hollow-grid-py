"""Short standing tokens for player.read and grid.who."""

from __future__ import annotations

from hollow_grid.world.brand import brand
from hollow_grid.world.model import Player


def regard(player: Player) -> str:
    if player.ashsworn:
        return "branded"
    if player.morality >= 50:
        return "honored"
    if player.morality <= -50:
        return "feared"
    if player.faction == "ally":
        return "trusted"
    if player.faction == "front":
        return "front"
    return "neutral"


def tagged(player: Player) -> str:
    name = player.name
    if player.title:
        name += ", " + player.title
    b = brand(player)
    if b:
        return name + " (" + b + ")"
    return name
