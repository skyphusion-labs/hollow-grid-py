"""Line-driven session for the Worker Durable Object.

The process server reads the socket in a loop. A Worker cannot. This module
feeds one line at a time into the same Session and Gameplay objects.
"""

from __future__ import annotations

import asyncio
from typing import Any

from hollow_grid import event
from hollow_grid.auth.passphrase import hash_passphrase, verify_passphrase
from hollow_grid.grid.sync import merge_hub_on_login_async
from hollow_grid.transport.federation import report_presence
from hollow_grid.transport.server import PendingRespawn, WorldServer
from hollow_grid.transport.session import BANNER, Session, _resume_line
from hollow_grid.transport.sanitize import sanitize_player_name
from hollow_grid.world.mobs import new_mob
from hollow_grid.world.model import Player
from hollow_grid.world.races import RACES, race_by_choice, race_by_id

def reject_worker_hub(hub_url: str) -> None:
    """The Worker cannot call the hub without blocking its one loop."""
    if hub_url.strip():
        raise RuntimeError(
            "The Worker refuses GRID_HUB_URL. Leave it empty. Federation stays on the process server."
        )


def task_mark() -> set[int]:
    """Ids of tasks that already exist. drain_spawned ignores these."""
    return {id(task) for task in asyncio.all_tasks()}


async def drain_spawned(before: set[int]) -> None:
    """Wait for tasks this turn spawned. Leave older tasks alone."""
    current = asyncio.current_task()
    for _ in range(25):
        pending = [
            task
            for task in asyncio.all_tasks()
            if task is not current and not task.done() and id(task) not in before
        ]
        if not pending:
            return
        await asyncio.wait(pending, timeout=0.2)


LIVE_FIELDS = (
    "room_id",
    "hp",
    "max_hp",
    "position",
    "poisoned",
    "addiction",
    "inventory",
    "equipment",
    "trait_ready_at",
)


def cf_init(session: Session) -> None:
    session._cf_phase = "name"
    session._cf_name = ""
    session._cf_reserved = False
    session._cf_registered = False
    session._cf_new = False
    session._cf_race_id = ""


async def cf_begin(session: Session) -> None:
    cf_init(session)
    session._line(BANNER)
    session._line("By what name are you known, wanderer?")
    await session._flush()


async def cf_feed(session: Session, line: str) -> bool:
    """Handle one line. Return True when the socket should close."""
    phase = session._cf_phase
    if phase == "closed":
        return True
    if phase == "name":
        return await _on_name(session, line)
    if phase == "admin":
        return await _on_admin(session, line)
    if phase == "race":
        return await _on_race(session, line)
    if phase == "passphrase":
        return await _on_passphrase(session, line)
    if phase == "play":
        return await _on_play(session, line)
    return True


async def cf_close(session: Session) -> None:
    if session._cf_phase == "closed" and not session._cf_registered and not session._cf_reserved:
        return
    if session._cf_registered and session._player is not None:
        await session._disconnect(session._player.name)
        await session._hub.unregister(session._player.name)
    elif session._cf_reserved and session._cf_name:
        await session._hub.release(session._cf_name)
    session._cf_reserved = False
    session._cf_registered = False
    session._cf_phase = "closed"


async def federation_tick(server: WorldServer) -> None:
    """Poll local gridcasts. The Worker does not call a remote hub."""
    from hollow_grid.grid.async_rpc import grid_rpc
    from hollow_grid.transport.federation import advance_cast_cursor

    grid = server.grid
    if grid is None:
        return
    if not grid.remote():
        await server.poll_gridcasts()
        return
    if not server._cf_cursor_ready:
        try:
            if server.last_cast == 0:
                server.last_cast = await advance_cast_cursor(grid)
        except Exception as exc:
            server.log.warning(
                "grid cast cursor init failed world=%s err=%s",
                server.world.name,
                exc,
            )
        server._cf_cursor_ready = True
    url = (server.world.url or "").strip()
    if url and not server._cf_registered_hub:
        try:
            await grid_rpc(grid, grid.register, server.world.name, url)
            server._cf_registered_hub = True
            server.log.info("registered on the Grid world=%s url=%s", server.world.name, url)
        except Exception as exc:
            server.log.warning(
                "grid register failed world=%s err=%s",
                server.world.name,
                exc,
            )
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
    except Exception as exc:
        server.log.warning(
            "federation tide poll failed world=%s err=%s",
            server.world.name,
            exc,
        )
    await report_presence(server)


async def cf_tick(session: Session) -> None:
    if session._cf_phase != "play" or session._player is None:
        return
    session._on_tick()
    await session._flush()


async def bind_send(session: Session) -> None:
    if session._player is None:
        return
    lp = await session._hub.find(session._player.name)
    if lp is None:
        return
    sock = session._ws

    def send(text: str) -> None:
        now = getattr(sock, "send_now", None)
        if now is not None:
            now(text)
            return
        result = sock.send(text)
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)

    lp.send = send


def live_blob(session: Session) -> dict[str, Any]:
    player = session._player
    if player is None:
        return {}
    blob: dict[str, Any] = {name: getattr(player, name) for name in LIVE_FIELDS}
    blob["inventory"] = list(player.inventory)
    blob["equipment"] = dict(player.equipment)
    blob["target_id"] = player.target.id if player.target is not None else ""
    blob["entered"] = session._entered
    blob["resolved"] = sorted(session._resolved)
    blob["treat_ready_at"] = session._treat_ready_at
    return blob


def apply_live(session: Session, blob: dict[str, Any]) -> None:
    player = session._player
    if player is None or not blob:
        return
    for name in LIVE_FIELDS:
        if name in blob:
            setattr(player, name, blob[name])
    if isinstance(blob.get("inventory"), list):
        player.inventory = [str(item) for item in blob["inventory"]]
    if isinstance(blob.get("equipment"), dict):
        player.equipment = {str(key): str(value) for key, value in blob["equipment"].items()}
    target_id = str(blob.get("target_id") or "")
    player.target = None
    if target_id:
        for room in session._world.rooms.values():
            for mob in room.mobs:
                if mob.id == target_id:
                    player.target = mob
                    break
            if player.target is not None:
                break
    session._entered = bool(blob.get("entered", False))
    session._resolved = set(blob.get("resolved") or [])
    session._treat_ready_at = int(blob.get("treat_ready_at") or 0)


def snapshot_world(server: WorldServer) -> dict[str, Any]:
    mobs: list[dict[str, Any]] = []
    for room in server.world.rooms.values():
        for mob in room.mobs:
            mobs.append({"id": mob.id, "room": room.id, "hp": mob.hp, "max_hp": mob.max_hp})
    dead = [
        {"id": pending.template_id, "room": pending.room_id, "at": pending.at}
        for pending in server.dead_mobs.values()
    ]
    return {
        "mobs": mobs,
        "dead": dead,
        "caches": dict(server.caches),
        "cages": dict(server.cages),
        "forgiven": [list(pair) for pair in server.forgiven],
        "saved": {key: list(names) for key, names in server.saved.items()},
        "deeds": {key: dict(counts) for key, counts in server.deeds.items()},
        "kept": [list(pair) for pair in server.kept],
        "last_tide": server.last_tide,
        "last_cast": server.last_cast,
        "mob_slain_at": dict(server.mob_slain_at),
        "grid_hub_detached": server.grid_hub_detached,
    }


def apply_snapshot(server: WorldServer, data: dict[str, Any]) -> None:
    for room in server.world.rooms.values():
        room.mobs.clear()
    for row in data.get("mobs") or []:
        if not isinstance(row, dict):
            continue
        try:
            mob = new_mob(str(row.get("id") or ""))
        except KeyError:
            continue
        mob.hp = int(row.get("hp", mob.hp))
        mob.max_hp = int(row.get("max_hp", mob.max_hp))
        home = server.world.room(str(row.get("room") or ""))
        if home is not None:
            home.mobs.append(mob)
    server.dead_mobs = {}
    for row in data.get("dead") or []:
        if not isinstance(row, dict):
            continue
        mob_id = str(row.get("id") or "")
        if not mob_id:
            continue
        server.dead_mobs[mob_id] = PendingRespawn(
            template_id=mob_id,
            room_id=str(row.get("room") or ""),
            at=int(row.get("at") or 0),
        )
    server.caches = {str(key): int(value) for key, value in dict(data.get("caches") or {}).items()}
    server.cages = {str(key): int(value) for key, value in dict(data.get("cages") or {}).items()}
    server.forgiven = set()
    for pair in data.get("forgiven") or []:
        if isinstance(pair, list) and len(pair) == 2:
            server.forgiven.add((str(pair[0]), str(pair[1])))
    server.saved = {
        str(key): [str(name) for name in names]
        for key, names in dict(data.get("saved") or {}).items()
        if isinstance(names, list)
    }
    server.deeds = {}
    for key, counts in dict(data.get("deeds") or {}).items():
        if isinstance(counts, dict):
            server.deeds[str(key)] = {str(kind): int(count) for kind, count in counts.items()}
    server.kept = set()
    for pair in data.get("kept") or []:
        if isinstance(pair, list) and len(pair) == 2:
            server.kept.add((str(pair[0]), str(pair[1])))
    server.last_tide = int(data.get("last_tide") or 0)
    server.last_cast = int(data.get("last_cast") or 0)
    server.mob_slain_at = {
        str(key): int(value) for key, value in dict(data.get("mob_slain_at") or {}).items()
    }
    server.grid_hub_detached = bool(data.get("grid_hub_detached"))


async def prepare_restored(session: Session) -> bool:
    """Re-arm a socket after hibernation. Return False when the socket should close."""
    if session._cf_phase == "play":
        return True
    if session._cf_reserved and session._cf_name:
        if not await session._hub.try_reserve(session._cf_name):
            return False
    if session._cf_phase != "passphrase":
        return True
    if session._cf_new:
        race = race_by_id(session._cf_race_id)
        if race is None:
            return False
        session._player = Player.new(session._cf_name, race, session._world.start().id)
        session._cf_stored_hash = ""
        return True
    sheet, found = session._store.load(session._cf_name)
    if not found:
        return False
    session._player = Player.from_sheet(session._cf_name, sheet, session._world.start().id)
    session._cf_stored_hash = sheet.secret_hash
    return True


async def restore_player(session: Session, blob: dict[str, Any]) -> bool:
    """Rebuild a playing session after the Durable Object wakes. Return False to drop it."""
    name = session._cf_name
    if not name:
        return False
    sheet, found = session._store.load(name)
    if not found:
        return False
    player = Player.from_sheet(name, sheet, session._world.start().id)
    session._player = player
    apply_live(session, blob)
    push = await session._hub.register(player)
    if push is None:
        session._player = None
        return False
    session._cf_registered = True
    session._cf_reserved = False
    await session._hub.sync(player)
    await bind_send(session)
    return True


async def _on_name(session: Session, line: str) -> bool:
    if not line:
        return True
    clean = sanitize_player_name(line)
    if not clean:
        session._line("That name will not hold on the Grid. Use 2-32 letters, digits, dash, or underscore.")
        await session._flush()
        return False
    if not await session._hub.try_reserve(clean):
        session._line("")
        session._line(
            "That name is already awake on the Grid elsewhere. "
            "Wait, or choose another path."
        )
        await session._flush()
        return True
    session._cf_name = clean
    session._cf_reserved = True
    if session._server.is_admin(clean):
        session._line("The Grid remembers keepers. Speak the keeper's token:")
        await session._flush()
        session._cf_phase = "admin"
        return False
    return await _after_gate(session)


async def _on_admin(session: Session, line: str) -> bool:
    if not session._server.verify_admin_token(line):
        session._line("The Grid does not recognize you as keeper.")
        await session._flush()
        return await _drop(session)
    return await _after_gate(session)


async def _after_gate(session: Session) -> bool:
    name = session._cf_name
    sheet, found = session._store.load(name)
    if found:
        session._cf_new = False
        session._player = Player.from_sheet(name, sheet, session._world.start().id)
        return await _prompt_passphrase(session, sheet.secret_hash)
    session._cf_new = True
    session._line("")
    session._line("The Grid does not know the name " + name + ". A new mind, then.")
    session._cf_phase = "race"
    await _prompt_race(session)
    return False


async def _on_race(session: Session, line: str) -> bool:
    chosen = race_by_choice(line)
    if chosen is None:
        session._line("The Grid does not recognize that shape.")
        await _prompt_race(session)
        return False
    session._cf_race_id = chosen.id
    session._player = Player.new(session._cf_name, chosen, session._world.start().id)
    return await _prompt_passphrase(session, "")


async def _prompt_race(session: Session) -> None:
    session._line("")
    session._line("Before the Grid will hold your name, choose what you are:")
    for index, race in enumerate(RACES, start=1):
        session._line(f"  {index}) {race.name} -- {race.blurb}")
    session._line("Type a number or a name.")
    session._emit_race_prompt()
    await session._flush()


async def _prompt_passphrase(session: Session, stored_hash: str) -> bool:
    session._cf_phase = "passphrase"
    session._cf_stored_hash = stored_hash
    if stored_hash:
        session._line("")
        session._line("By what secret phrase do you prove yourself?")
    else:
        session._line("")
        session._line(
            "Choose a secret phrase only you will know. "
            "The Grid will ask for it when you return."
        )
    await session._flush()
    return False


async def _on_passphrase(session: Session, line: str) -> bool:
    if not line:
        return await _drop(session)
    stored_hash = session._cf_stored_hash
    if not stored_hash:
        try:
            secret = hash_passphrase(line)
        except ValueError:
            session._line("That phrase will not do. Choose one at least eight characters long.")
            await session._flush()
            return await _drop(session)
        assert session._player is not None
        session._player.secret_hash = secret
        await session._persist_async()
        if session._cf_new:
            race = race_by_id(session._player.race)
            race_name = race.name if race is not None else session._player.race
            session._log.info("player created name=%s race=%s", session._player.name, session._player.race)
            session._line("")
            session._line(
                "The Grid takes your name and your shape, "
                + race_name
                + ". Type 'help' if you need a refresher; it is watching what you choose."
            )
        else:
            session._log.info("player resumed name=%s race=%s", session._player.name, session._player.race)
            session._line("")
            session._line(
                "Welcome back to the wastes, "
                + session._player.name
                + ". (Type 'help' if you need a refresher.) "
                + _resume_line(session._player)
            )
        return await _enter(session)
    if not verify_passphrase(line, stored_hash):
        session._line("The Grid does not recognize that phrase for this name.")
        await session._flush()
        return await _drop(session)
    assert session._player is not None
    session._log.info("player resumed name=%s race=%s", session._player.name, session._player.race)
    session._line("")
    session._line(
        "Welcome back to the wastes, "
        + session._player.name
        + ". (Type 'help' if you need a refresher.) "
        + _resume_line(session._player)
    )
    return await _enter(session)


async def _enter(session: Session) -> bool:
    assert session._player is not None
    push = await session._hub.register(session._player)
    if push is None:
        session._line("")
        session._line(
            "That name is already awake on the Grid elsewhere. "
            "Wait, or choose another path."
        )
        await session._flush()
        return await _drop(session)
    session._cf_registered = True
    session._cf_reserved = False
    await bind_send(session)
    await merge_hub_on_login_async(session._server, session._player)
    await session._hub.sync(session._player)
    await report_presence(session._server)
    await session._hub.broadcast_room(
        session._player.room_id,
        session._player.name + " steps out of the haze.",
        session._player.name,
    )
    session._entered = True
    session._event(event.WORLD_STATE, session._world.state())
    await session._send_scene()
    await session._flush()
    session._cf_phase = "play"
    return False


async def _on_play(session: Session, line: str) -> bool:
    if await session._handle_command(line):
        await cf_close(session)
        return True
    return False


async def _drop(session: Session) -> bool:
    if session._cf_reserved and session._cf_name:
        await session._hub.release(session._cf_name)
    session._cf_reserved = False
    session._cf_phase = "closed"
    return True
