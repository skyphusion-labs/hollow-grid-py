"""Background federation heartbeats when connected to a remote Grid Hub."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from hollow_grid.grid.async_rpc import grid_rpc
from hollow_grid.grid.open import GridHub
from hollow_grid.grid.remote import GridHubError
from hollow_grid.world.brand import brand
from hollow_grid.world.model import Player

if TYPE_CHECKING:
    from hollow_grid.transport.server import WorldServer

_CAST_CURSOR_BATCH = 50
_CAST_CURSOR_MAX_STEPS = 100


async def advance_cast_cursor(grid: GridHub) -> int:
    """Fast-forward the poll cursor without relaying stale hub backlog (TS persists last_cast)."""
    since = 0
    max_id = 0
    for _ in range(_CAST_CURSOR_MAX_STEPS):
        batch = await grid_rpc(grid, grid.casts_since, since, _CAST_CURSOR_BATCH)
        if not batch:
            break
        max_id = max(c.id for c in batch)
        since = max_id
        if len(batch) < _CAST_CURSOR_BATCH:
            break
    return max_id


async def run_federation(server: WorldServer, *, default_port: int) -> None:
    grid = server.grid
    if grid is None or not grid.remote():
        return

    url = server.world.url.strip()
    if not url:
        url = f"ws://127.0.0.1:{default_port}/ws"

    try:
        server.last_cast = await advance_cast_cursor(grid)
    except GridHubError as exc:
        server.log.warning("grid cast cursor init failed world=%s err=%s", server.world.name, exc)

    try:
        await grid_rpc(grid, grid.register, server.world.name, url)
        server.log.info("registered on the Grid world=%s url=%s", server.world.name, url)
    except GridHubError as exc:
        server.log.warning("grid register failed world=%s err=%s", server.world.name, exc)

    while True:
        await asyncio.sleep(2)
        if grid.remote():
            try:
                await server.poll_gridcasts()
            except Exception as exc:
                server.log.warning(
                    "federation gridcast poll failed world=%s err=%s",
                    server.world.name,
                    exc,
                )
        try:
            tide = await grid_rpc(grid, grid.tide)
            async with server._lock:
                server.last_tide = tide
        except GridHubError:
            pass
        await report_presence(server)


async def report_presence(server: WorldServer) -> None:
    grid = server.grid
    if grid is None or not grid.remote():
        return
    players = await server.hub.all_players()
    if not players:
        return
    entries: list[dict[str, str]] = []
    for lp in players:
        stub = Player(
            name=lp.name,
            race=lp.race,
            room_id=lp.room,
            hp=lp.hp,
            max_hp=lp.max_hp,
            faction=lp.faction,
            morality=lp.morality,
            ashsworn=lp.ashsworn,
        )
        entries.append({"name": lp.name, "regard": brand(stub), "title": lp.title})
    try:
        await grid_rpc(
            grid,
            grid.report_presence,
            server.world.name,
            entries,
            int(time.time() * 1000),
        )
    except GridHubError:
        pass
