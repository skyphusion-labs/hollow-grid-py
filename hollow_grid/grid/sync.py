"""Federation character sheet merge/commit (mirrors hollow-grid-go grid_cmds.go)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hollow_grid.grid.local_hub import CharSheet as HubCharSheet
from hollow_grid.grid.remote import GridHubError
from hollow_grid.world.model import canonical_faction, max_hp_for
from hollow_grid.world.races import race_by_id

if TYPE_CHECKING:
    from hollow_grid.grid.open import GridHub
    from hollow_grid.transport.server import WorldServer
    from hollow_grid.world.model import Player


def hub_sheet(player: Player) -> HubCharSheet:
    return HubCharSheet(
        level=player.level,
        xp=player.xp,
        gold=player.gold,
        faction=canonical_faction(player.faction),
        morality=player.morality,
        title=player.title,
        race=player.race,
        ashsworn=player.ashsworn,
    )


def apply_hub_sheet(player: Player, sheet: HubCharSheet) -> None:
    if sheet.level > 0:
        player.level = sheet.level
    player.xp = sheet.xp
    if sheet.gold > 0 or sheet.race:
        player.gold = sheet.gold
    if sheet.faction:
        player.faction = canonical_faction(sheet.faction)
    player.morality = sheet.morality
    player.title = sheet.title
    if sheet.race:
        player.race = sheet.race
    if sheet.ashsworn:
        player.ashsworn = True
    race = race_by_id(player.race)
    player.max_hp = max_hp_for(player.level, race.hp_mod)
    if player.hp > player.max_hp:
        player.hp = player.max_hp


def merge_hub_on_login(server: WorldServer, player: Player) -> None:
    grid = server.grid
    if grid is None or not grid.remote():
        return
    try:
        canon, _ = grid.load_character(player.name)
    except GridHubError:
        return
    apply_hub_sheet(player, canon)

    async def _register() -> None:
        assert server.grid is not None
        url = server.world.url or "ws://127.0.0.1:8791/ws"
        try:
            server.grid.register(server.world.name, url)
        except GridHubError:
            pass

    asyncio.create_task(_register())


def commit_hub(server: WorldServer, player: Player | None) -> None:
    grid = server.grid
    if player is None or grid is None or not grid.remote():
        return
    try:
        grid.commit_character(player.name, hub_sheet(player))
    except GridHubError:
        pass
