"""HTTP health probes and the /ws player transport."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from hollow_grid import event
from hollow_grid.grid.async_rpc import grid_rpc
from hollow_grid.grid.open import GridHub, open_grid_hub
from hollow_grid.grid.remote import GridHubError
from hollow_grid.transport.federation import run_federation
from hollow_grid.store import CharStore, FileStore
from hollow_grid.transport.hub import Hub
from hollow_grid.transport.mapsvg import MAPSVG
from hollow_grid.transport.session import Session, WORLD_HEARTBEAT_SEC
from hollow_grid.transport.webclient import play_page
from hollow_grid.world import DEFAULT_WORLD_NAME, DEFAULT_WORLD_URL, World, build_world
from hollow_grid.world.mobs import respawn_for

DEFAULT_ADDR = "127.0.0.1"
DEFAULT_PORT = 8791
CAGE_REFILL_MS = 4 * 60 * 1000
WARDEN_GRACE_MS = 180_000
AMBIENT_LEDGER_KINDS = ("ghost", "passage", "recall")


@dataclass
class PendingRespawn:
    template_id: str
    room_id: str
    at: int


@dataclass
class WorldServer:
    world: World
    store: CharStore
    hub: Hub = field(default_factory=Hub)
    grid: GridHub | None = None
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("hollow_grid"))
    admins: dict[str, bool] = field(default_factory=dict)
    caches: dict[str, int] = field(default_factory=dict)
    local_traces: dict[str, list] = field(default_factory=dict)
    forgiven: set[tuple[str, str]] = field(default_factory=set)
    cages: dict[str, int] = field(default_factory=dict)
    saved: dict[str, list[str]] = field(default_factory=dict)
    deeds: dict[str, dict[str, int]] = field(default_factory=dict)
    kept: set[tuple[str, str]] = field(default_factory=set)
    dead_mobs: dict[str, PendingRespawn] = field(default_factory=dict)
    mob_slain_at: dict[str, int] = field(default_factory=dict)
    last_tide: int = 0
    last_cast: int = 0
    grid_hub_detached: bool = False
    _sessions: int = 0
    _idle: asyncio.Event = field(default_factory=asyncio.Event)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if self.grid is None:
            self.grid = open_grid_hub(self.world.name, self.world.url)
        self._idle.set()

    def is_admin(self, name: str) -> bool:
        return name.strip().casefold() in self.admins

    async def tide(self) -> int:
        assert self.grid is not None
        t = self.grid.tide()
        async with self._lock:
            self.last_tide = t
        return t

    def cached_tide(self) -> int:
        return self.last_tide

    def cache_gold(self, room: str) -> int:
        return self.caches.get(room, 0)

    def add_cache(self, room: str, amount: int) -> None:
        self.caches[room] = self.caches.get(room, 0) + amount

    def take_cache(self, room: str) -> int:
        g = self.caches.get(room, 0)
        self.caches[room] = 0
        return g

    def has_forgiven(self, forgiver: str, subject: str) -> bool:
        return (forgiver, subject) in self.forgiven

    def mark_forgiven(self, forgiver: str, subject: str) -> None:
        self.forgiven.add((forgiver, subject))

    def cages_ready(self, room: str) -> bool:
        at = self.cages.get(room, 0)
        return at == 0 or int(time.time() * 1000) >= at

    def set_cage_refill(self, room: str) -> None:
        self.cages[room] = int(time.time() * 1000) + CAGE_REFILL_MS

    def remember_saved(self, player: str, *names: str) -> None:
        rows = list(names) + self.saved.get(player, [])
        self.saved[player] = rows[:24]

    def saved_souls(self, player: str) -> list[str]:
        return list(self.saved.get(player, []))

    def add_deed(self, player: str, kind: str) -> None:
        d = self.deeds.setdefault(player, {})
        d[kind] = d.get(kind, 0) + 1

    def deeds_for(self, player: str) -> dict[str, int]:
        return dict(self.deeds.get(player, {}))

    def has_kept(self, keeper: str, fallen: str) -> bool:
        return (keeper, fallen) in self.kept

    def mark_kept(self, keeper: str, fallen: str) -> None:
        self.kept.add((keeper, fallen))

    def persist_player(self, player: Any) -> None:
        if player is None or not player.name:
            return
        try:
            self.store.commit(player.name, player.sheet())
        except Exception:
            pass

    def warden_cleared(self) -> bool:
        room = self.world.room("holding_pit")
        if room is None:
            return True
        if room.mob("warden") is None:
            return True
        slain = self.mob_slain_at.get("warden", 0)
        return slain > 0 and int(time.time() * 1000) - slain < WARDEN_GRACE_MS

    def kill_mob(self, room_id: str, mob: Any) -> None:
        if mob is None:
            return
        self.world.remove_mob(room_id, mob)
        info = respawn_for(mob.id)
        if info is None:
            return
        spawn_room, respawn_ms = info
        now_ms = int(time.time() * 1000)
        self.mob_slain_at[mob.id] = now_ms
        self.dead_mobs[mob.id] = PendingRespawn(
            template_id=mob.id,
            room_id=spawn_room or room_id,
            at=now_ms + respawn_ms,
        )

    def tick_respawns(self) -> None:
        now = int(time.time() * 1000)
        due = [p for mid, p in list(self.dead_mobs.items()) if p.at <= now]
        for p in due:
            self.dead_mobs.pop(p.template_id, None)
            if self.world.has_mob(p.template_id):
                continue
            m = self.world.spawn_mob(p.template_id)
            if m is None:
                continue
            name = m.name
            if name:
                name = name[0].upper() + name[1:]
            prose = name + " stalks into view.\r\n"
            asyncio.create_task(self.hub.broadcast_room(p.room_id, prose, ""))

    def contribute_tide(self, delta: int) -> None:
        grid = self.grid
        if grid is None:
            return
        if grid.remote():
            asyncio.create_task(self._shift_tide_async(delta))
            return
        self.last_tide = grid.shift_tide(delta)

    async def _shift_tide_async(self, delta: int) -> None:
        grid = self.grid
        if grid is None:
            return
        try:
            t = await grid_rpc(grid, grid.shift_tide, delta)
            async with self._lock:
                self.last_tide = t
        except GridHubError:
            pass

    def record_local_trace(self, node: str, kind: str, text: str) -> None:
        from hollow_grid.grid.local_hub import EchoTrace

        rows = self.local_traces.setdefault(node, [])
        rows.insert(0, EchoTrace(at=int(time.time() * 1000), kind=kind, text=text))
        if len(rows) > 50:
            self.local_traces[node] = rows[:50]
        if self.grid is not None:
            self.grid.record_local(node, kind, text)

    def local_traces_for(self, node: str, limit: int) -> list:
        rows = self.local_traces.get(node, [])
        if limit <= 0 or limit >= len(rows):
            return list(rows)
        return rows[:limit]

    def all_local_traces(self, limit: int) -> list:
        out: list = []
        for rows in self.local_traces.values():
            out.extend(rows)
        out.sort(key=lambda r: r.at, reverse=True)
        if limit > 0:
            out = out[:limit]
        return out

    async def handle_ws(self, ws: ServerConnection) -> None:
        self._sessions += 1
        self._idle.clear()
        try:
            await Session(ws, self).run()
        finally:
            self._sessions -= 1
            if self._sessions == 0:
                self._idle.set()

    async def wait_idle(self) -> None:
        await self._idle.wait()

    def health_json(self) -> dict[str, Any]:
        return {"ok": True, "ts": int(time.time() * 1000), "world": self.world.name}

    def health_deep_json(self) -> tuple[int, dict[str, Any]]:
        world_ok = self.world.start() is not None
        hub_ok = True
        hub_latency = 0
        if self.grid is not None and self.grid.remote():
            start = time.time()
            try:
                self.grid.ping()
            except GridHubError:
                hub_ok = False
            hub_latency = int((time.time() - start) * 1000)
        checks = {
            "world": {"ok": world_ok, "latency_ms": 0, "critical": True},
            "grid_hub": {"ok": hub_ok, "latency_ms": hub_latency, "critical": False},
        }
        code = 200 if world_ok else 503
        body = {
            "ok": world_ok,
            "ts": int(time.time() * 1000),
            "world": self.world.name,
            "checks": checks,
        }
        return code, body

    async def poll_gridcasts(self) -> None:
        assert self.grid is not None
        try:
            casts = self.grid.casts_since(self.last_cast, 20)
        except GridHubError:
            return
        if not casts:
            return
        max_id = self.last_cast
        for c in casts:
            if c.id > max_id:
                max_id = c.id
            ev = event.line(
                event.COMM_GRIDCAST,
                {"world": c.world, "from": c.sender, "text": c.text},
            )
            prose = f"\r\n[Grid] [{c.world}] {c.sender}: {c.text}\r\n"
            await self.hub.broadcast_all(prose + ev + "\r\n")
        self.last_cast = max_id


def _json_response(code: int, body: dict[str, Any]) -> Response:
    reason = "OK" if code == 200 else "Service Unavailable"
    payload = json.dumps(body).encode("utf-8")
    headers = Headers([("Content-Type", "application/json")])
    return Response(code, reason, headers, payload)


def _svg_response(body: str) -> Response:
    headers = Headers([("Content-Type", "image/svg+xml; charset=utf-8")])
    return Response(200, "OK", headers, body.encode("utf-8"))


def _parse_admins(raw: str) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for part in raw.split(","):
        name = part.strip().casefold()
        if name:
            out[name] = True
    return out


async def run_server(
    *,
    host: str = DEFAULT_ADDR,
    port: int = DEFAULT_PORT,
    world_name: str = DEFAULT_WORLD_NAME,
    world_url: str = DEFAULT_WORLD_URL,
    data_dir: str = "data",
    admins: str | None = None,
    grid_hub_url: str | None = None,
    grid_hub_token: str | None = None,
) -> WorldServer:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("hollow_grid")
    store = FileStore(data_dir)
    world = build_world(world_name, world_url)
    admin_raw = admins if admins is not None else os.environ.get("ADMINS", "skyphusion")
    grid = open_grid_hub(world_name, world_url, hub_url=grid_hub_url, token=grid_hub_token)
    server = WorldServer(
        world=world,
        store=store,
        grid=grid,
        log=log,
        admins=_parse_admins(admin_raw),
    )
    if grid.remote():
        log.info("federation enabled grid_hub=%s", grid_hub_url or os.environ.get("GRID_HUB_URL", ""))

    fed_task = asyncio.create_task(run_federation(server, default_port=port))

    async def world_loop() -> None:
        try:
            while True:
                await asyncio.sleep(WORLD_HEARTBEAT_SEC)
                server.tick_respawns()
                await server.poll_gridcasts()
        except asyncio.CancelledError:
            raise

    loop_task = asyncio.create_task(world_loop())

    async def handle_ws(ws: ServerConnection) -> None:
        await server.handle_ws(ws)

    async def process_request(_connection: ServerConnection, request: Request) -> Response | None:
        path = request.path.split("?", 1)[0]
        if path == "/health":
            return _json_response(200, server.health_json())
        if path == "/health/deep":
            code, body = server.health_deep_json()
            return _json_response(code, body)
        if path == "/map.svg":
            return _svg_response(MAPSVG)
        if path == "/ws":
            return None
        page_html = play_page(server.world.name).encode("utf-8")
        headers = Headers([("Content-Type", "text/html; charset=utf-8")])
        return Response(200, "OK", headers, page_html)

    async with serve(
        handle_ws,
        host,
        port,
        process_request=process_request,
        server_header=None,
    ):
        log.info("listening on ws://%s:%s/ws world=%s", host, port, world_name)
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            loop_task.cancel()
            fed_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await loop_task
            with contextlib.suppress(asyncio.CancelledError):
                await fed_task
            await server.wait_idle()
            raise

    return server
