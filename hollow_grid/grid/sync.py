"""Federation character sheet merge/commit (mirrors hollow-grid-go grid_cmds.go)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from hollow_grid.grid.local_hub import CharSheet as HubCharSheet
from hollow_grid.grid.async_rpc import grid_rpc
from hollow_grid.grid.remote import GridHubError
from hollow_grid.world.model import canonical_faction, max_hp_for
from hollow_grid.world.races import race_by_id

if TYPE_CHECKING:
    from hollow_grid.grid.open import GridHub
    from hollow_grid.transport.server import WorldServer
    from hollow_grid.world.model import Player

log = logging.getLogger(__name__)


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
    # TS reference (world.ts:798): hub is authoritative on faction at login, including "none".
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


async def merge_hub_on_login_async(server: WorldServer, player: Player) -> None:
    grid = server.grid
    if grid is None or not grid.remote():
        return
    try:
        canon, _ = await grid_rpc(grid, grid.load_character, player.name)
    except GridHubError:
        return
    apply_hub_sheet(player, canon)

    async def _register() -> None:
        assert server.grid is not None
        url = server.world.url or "ws://127.0.0.1:8791/ws"
        try:
            await grid_rpc(server.grid, server.grid.register, server.world.name, url)
        except GridHubError as exc:
            log.warning("grid register failed world=%s err=%s", server.world.name, exc)

    asyncio.create_task(_register())


async def commit_hub_async(server: WorldServer, player: Player | None) -> bool:
    """Commit canonical sheet off the event loop. Returns True when the write landed."""
    grid = server.grid
    if player is None or grid is None or not grid.remote():
        return True
    last_err: GridHubError | None = None
    sheet = hub_sheet(player)
    for attempt in range(2):
        try:
            await grid_rpc(grid, grid.commit_character, player.name, sheet)
            server.grid_hub_detached = False
            return True
        except GridHubError as exc:
            last_err = exc
            log.warning(
                "grid commitCharacter failed name=%s attempt=%d err=%s",
                player.name,
                attempt + 1,
                exc,
            )
    server.grid_hub_detached = True
    log.error(
        "grid commitCharacter failed after retry name=%s err=%s",
        player.name,
        last_err,
    )
    return False

