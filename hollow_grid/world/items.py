"""Local salvage items and player inventory/equipment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hollow_grid.world.model import Player

EQUIP_SLOTS = ("weapon", "head", "body", "hands", "feet")
STARTER_WEAPON = "shiv"


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    slot: str = ""
    damage: int = 0
    armor: int = 0


ITEMS: dict[str, Item] = {
    "shiv": Item("shiv", "a rusted shiv", "weapon", damage=3),
    "rebar": Item("rebar", "a length of rebar", "weapon", damage=6),
    "helm": Item("helm", "a dented scrap helm", "head", armor=1),
    "plating": Item("plating", "a sheet of scrap plating", "body", armor=2),
    "charm": Item("charm", "an elven charm"),
    "antidote": Item("antidote", "an antidote vial"),
    "dust": Item("dust", "a packet of dust"),
    "shard": Item("shard", "the core shard"),
}


def item_by_id(item_id: str) -> Item | None:
    return ITEMS.get(item_id)


def item_name(item_id: str) -> str:
    it = ITEMS.get(item_id)
    return it.name if it else item_id


def equip_payload(player: Player) -> dict[str, Any]:
    def slot(name: str) -> str | None:
        return player.equipment.get(name)

    return {
        "weapon": slot("weapon"),
        "head": slot("head"),
        "body": slot("body"),
        "hands": slot("hands"),
        "feet": slot("feet"),
    }


def find_inventory(player: Player, arg: str) -> str | None:
    arg = arg.strip().casefold()
    if not arg:
        return None
    for item_id in player.inventory:
        if item_id == arg or arg in item_id.casefold() or arg in item_name(item_id).casefold():
            return item_id
    return None


def find_equipped(player: Player, arg: str) -> tuple[str, str] | None:
    arg = arg.strip().casefold()
    for slot, item_id in player.equipment.items():
        if item_id == arg or arg in item_id.casefold() or arg in item_name(item_id).casefold():
            return slot, item_id
    return None


def remove_from_inventory(player: Player, item_id: str) -> None:
    for i, have in enumerate(player.inventory):
        if have == item_id:
            del player.inventory[i]
            return


def wear(player: Player, arg: str) -> Item | None:
    item_id = find_inventory(player, arg)
    if item_id is None:
        return None
    it = item_by_id(item_id)
    if it is None or not it.slot:
        return None
    prev = player.equipment.get(it.slot)
    if prev:
        player.inventory.append(prev)
    remove_from_inventory(player, item_id)
    player.equipment[it.slot] = item_id
    return it


def unwear(player: Player, arg: str) -> Item | None:
    found = find_equipped(player, arg)
    if found is None:
        return None
    slot, item_id = found
    del player.equipment[slot]
    player.inventory.append(item_id)
    return item_by_id(item_id)


def has_item(player: Player, item_id: str) -> bool:
    return item_id in player.inventory


def add_item(player: Player, item_id: str) -> None:
    player.inventory.append(item_id)


def inventory_names(player: Player) -> list[str]:
    return [item_name(item_id) for item_id in player.inventory]
