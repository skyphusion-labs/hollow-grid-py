"""Cloudflare Worker entry for Verdigris Spool.

One Durable Object holds the world. Players speak WebSocket on /ws.
This module is the Workers runtime edge. Game rules stay in transport/.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from urllib.parse import urlparse

from hollow_grid.grid.local_hub import LocalHub
from hollow_grid.grid.open import open_grid_hub
from hollow_grid.store import MemoryStore
from hollow_grid.transport.cf_drive import (
    apply_snapshot,
    cf_begin,
    cf_close,
    cf_feed,
    cf_init,
    cf_tick,
    federation_tick,
    live_blob,
    prepare_restored,
    restore_player,
    snapshot_world,
)
from hollow_grid.transport.mapsvg import MAPSVG
from hollow_grid.transport.server import WorldServer, _parse_admins
from hollow_grid.transport.session import Session
from hollow_grid.transport.webclient import play_page
from hollow_grid.world import DEFAULT_WORLD_NAME, build_world
from workers import DurableObject, Response, WorkerEntrypoint

LOGIN_TIMEOUT_MS = 120_000
TICK_MS = 2_000
MAX_SOCKETS = 64
MAX_SOCKETS_PER_IP = 8
MAX_MESSAGE_BYTES = 4_096
DEEP_HEALTH_CACHE_MS = 30_000

_deep_cache: dict[str, object] | None = None


class WorkerConn:
    """Session socket backed by a hibernating Durable Object WebSocket."""

    def __init__(self, ws: object) -> None:
        self._ws = ws

    def send_now(self, data: str) -> None:
        send = getattr(self._ws, "send")
        send(data)

    async def send(self, data: str) -> None:
        self.send_now(data)


class VerdigrisWorld(DurableObject):
    def __init__(self, ctx: object, env: object) -> None:
        super().__init__(ctx, env)
        self._server: WorldServer | None = None
        self._store: MemoryStore | None = None
        self._sessions: dict[str, Session] = {}
        self._boot: asyncio.Task[None] | None = None

    async def fetch(self, request: object) -> object:
        await self._ensure()
        path = urlparse(_text(getattr(request, "url", ""))).path
        if path == "/health":
            return Response("ok", status=200)
        headers = getattr(request, "headers", None)
        upgrade = _header(headers, "Upgrade")
        if upgrade.casefold() != "websocket":
            return Response("This endpoint speaks WebSocket. Try wscat -c <url>/ws.", status=426)
        sockets = _socket_list(self.ctx)
        if len(sockets) >= MAX_SOCKETS:
            return Response("Server full", status=503)
        client_ip = _header(headers, "CF-Connecting-IP")
        if client_ip and _ip_count(sockets, client_ip) >= MAX_SOCKETS_PER_IP:
            return Response("Too many connections from your address", status=429)
        pair = _websocket_pair()
        client, server = pair
        self.ctx.acceptWebSocket(server)
        session = self._new_session(server)
        session._cf_connected_at = int(time.time() * 1000)
        self._sessions[session._cf_id] = session
        _write_attachment(server, _attachment(session, client_ip))
        await cf_begin(session)
        await self._arm()
        return Response(None, status=101, web_socket=client)

    async def webSocketMessage(self, ws: object, message: object) -> None:
        await self._ensure()
        text = _message_text(message)
        if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
            _close(ws, 1009, "message too large")
            return
        att = _read_attachment(ws)
        session = self._sessions.get(str(att.get("id") or ""))
        if session is None:
            _close(ws, 1000, "login again")
            return
        server = self._server
        assert server is not None
        try:
            if session._cf_name:
                await self._hydrate(session._cf_name)
            if session._cf_phase == "name" and text:
                from hollow_grid.transport.sanitize import sanitize_player_name

                clean = sanitize_player_name(text)
                if clean:
                    await self._hydrate(clean)
            stop = await cf_feed(session, text.strip())
            await drain_spawned()
            await self._flush_store()
            await self._save_live(session)
            await self._save_world()
            _write_attachment(ws, _attachment(session, str(att.get("ip") or "")))
            if stop:
                await cf_close(session)
                self._sessions.pop(session._cf_id, None)
                _close(ws, 1000, "bye")
        except Exception:
            server.log.exception(
                "worker command failed name=%s phase=%s",
                session._cf_name,
                session._cf_phase,
            )
            _send(ws, "The Grid stumbles. Try that again.\r\n")

    async def webSocketClose(self, ws: object, code: int, reason: str, was_clean: bool) -> None:
        del code, reason, was_clean
        await self._ensure()
        att = _read_attachment(ws)
        session = self._sessions.pop(str(att.get("id") or ""), None)
        if session is not None:
            await cf_close(session)
            await self._flush_store()
            await self._save_live(session)
            await self._save_world()
        _close(ws, 1000, "bye")

    async def alarm(self) -> None:
        try:
            await self._ensure()
            server = self._server
            if server is None:
                return
            now = int(time.time() * 1000)
            server.tick_respawns()
            await federation_tick(server)
            for ws in _socket_list(self.ctx):
                att = _read_attachment(ws)
                session = self._sessions.get(str(att.get("id") or ""))
                if session is None:
                    continue
                if session._cf_phase != "play" and now - session._cf_connected_at > LOGIN_TIMEOUT_MS:
                    await cf_close(session)
                    self._sessions.pop(session._cf_id, None)
                    _close(ws, 1008, "login timeout")
                    continue
                await cf_tick(session)
                await self._save_live(session)
            await drain_spawned()
            await self._flush_store()
            await self._save_world()
        finally:
            if _socket_list(self.ctx):
                await self._arm()

    async def _ensure(self) -> None:
        if self._server is not None:
            return
        if self._boot is None:
            self._boot = asyncio.create_task(self._boot_world())
        try:
            await self._boot
        except Exception:
            self._boot = None
            raise

    async def _boot_world(self) -> None:
        env = self.env
        world_name = _env(env, "WORLD_NAME", DEFAULT_WORLD_NAME)
        world_url = _env(env, "WORLD_URL", "")
        hub_url = _env(env, "GRID_HUB_URL", "")
        world = build_world(world_name, world_url)
        if hub_url:
            grid = open_grid_hub(
                world_name,
                world_url,
                hub_url=hub_url,
                token=_env(env, "GRID_HUB_TOKEN", ""),
                world_key=_env(env, "GRID_WORLD_KEY", ""),
            )
        else:
            grid = LocalHub(world_name, world_url)
        log = logging.getLogger("hollow_grid")
        if not log.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            log.addHandler(handler)
            log.setLevel(logging.INFO)
        store = MemoryStore()
        server = WorldServer(
            world=world,
            store=store,
            grid=grid,
            log=log,
            admins=_parse_admins(_env(env, "ADMINS", "skyphusion")),
            admin_token=_env(env, "ADMIN_TOKEN", ""),
        )
        self._store = store
        self._server = server
        raw_world = await self._get("world")
        if raw_world:
            try:
                loaded = json.loads(raw_world)
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                apply_snapshot(server, loaded)
        for ws in _socket_list(self.ctx):
            await self._restore_socket(ws)

    async def _restore_socket(self, ws: object) -> None:
        att = _read_attachment(ws)
        sid = str(att.get("id") or "")
        if not sid:
            return
        session = self._new_session(ws, sid=sid)
        session._cf_phase = str(att.get("phase") or "name")
        session._cf_name = str(att.get("name") or "")
        session._cf_reserved = bool(att.get("reserved"))
        session._cf_new = bool(att.get("is_new"))
        session._cf_race_id = str(att.get("race_id") or "")
        session._cf_connected_at = int(att.get("connected_at") or int(time.time() * 1000))
        self._sessions[sid] = session
        if session._cf_name:
            await self._hydrate(session._cf_name)
        if session._cf_phase == "play":
            blob = await self._load_live(session._cf_name)
            ok = await restore_player(session, blob)
        else:
            ok = await prepare_restored(session)
        if ok:
            return
        await cf_close(session)
        self._sessions.pop(sid, None)
        _close(ws, 1000, "login again")

    def _new_session(self, ws: object, sid: str = "") -> Session:
        server = self._server
        assert server is not None
        session = Session(WorkerConn(ws), server)  # type: ignore[arg-type]
        cf_init(session)
        session._cf_id = sid or uuid.uuid4().hex
        return session

    async def _hydrate(self, name: str) -> None:
        store = self._store
        if store is None or not name or store.seen(name):
            return
        store.remember_json(name, await self._get("char:" + _safe_key(name)))

    async def _flush_store(self) -> None:
        store = self._store
        if store is None:
            return
        for key, payload in store.dirty_json():
            await self._put("char:" + key, payload)

    async def _save_live(self, session: Session) -> None:
        if session._cf_phase != "play" or not session._cf_name:
            return
        from hollow_grid.store import name_key

        key = name_key(session._cf_name)
        if not key:
            return
        await self._put("live:" + key, json.dumps(live_blob(session)))

    async def _load_live(self, name: str) -> dict[str, object]:
        from hollow_grid.store import name_key

        key = name_key(name)
        if not key:
            return {}
        raw = await self._get("live:" + key)
        if not raw:
            return {}
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    async def _save_world(self) -> None:
        server = self._server
        if server is None:
            return
        await self._put("world", json.dumps(snapshot_world(server)))

    async def _get(self, key: str) -> str | None:
        raw = await self.ctx.storage.get(key)
        return _as_str(raw)

    async def _put(self, key: str, value: str) -> None:
        await self.ctx.storage.put(key, value)

    async def _arm(self) -> None:
        when = int(time.time() * 1000) + TICK_MS
        await self.ctx.storage.setAlarm(when)


class Default(WorkerEntrypoint):
    async def fetch(self, request: object) -> object:
        path = urlparse(_text(getattr(request, "url", ""))).path
        world_name = _env(self.env, "WORLD_NAME", DEFAULT_WORLD_NAME)
        if path == "/health":
            body = {"ok": True, "ts": int(time.time() * 1000), "world": world_name}
            return _json(body, 200)
        if path == "/health/deep":
            return await _health_deep(self.env, world_name)
        if path == "/map.svg":
            return Response(
                MAPSVG,
                headers={"content-type": "image/svg+xml; charset=utf-8"},
            )
        if path == "/ws":
            if not _origin_ok(request):
                return Response("Forbidden", status=403)
            headers = getattr(request, "headers", None)
            if _header(headers, "Upgrade").casefold() != "websocket":
                return Response("Expected a WebSocket upgrade.", status=426)
            stub = self.env.WORLD.getByName("world")
            return await stub.fetch(request)
        return Response(play_page(world_name), headers={"content-type": "text/html; charset=utf-8"})


def _origin_ok(request: object) -> bool:
    origin = _header(getattr(request, "headers", None), "Origin")
    if not origin:
        return True
    try:
        origin_host = urlparse(origin).netloc
    except ValueError:
        return False
    request_host = urlparse(_text(getattr(request, "url", ""))).netloc
    return bool(origin_host) and origin_host == request_host


async def _health_deep(env: object, world_name: str) -> object:
    global _deep_cache
    now = int(time.time() * 1000)
    if _deep_cache is not None and now - int(_deep_cache["at"]) < DEEP_HEALTH_CACHE_MS:
        return _json(_deep_cache["body"], int(_deep_cache["status"]))
    started = time.time()
    world_ok = False
    try:
        stub = getattr(env, "WORLD").getByName("world")
        res = await stub.fetch("https://world.internal/health")
        world_ok = int(getattr(res, "status", 0)) == 200
    except Exception:
        world_ok = False
    latency = int((time.time() - started) * 1000)
    status = 200 if world_ok else 503
    body = {
        "ok": world_ok,
        "ts": now,
        "world": world_name,
        "checks": {
            "world": {"ok": world_ok, "latency_ms": latency, "critical": True},
        },
    }
    _deep_cache = {"at": now, "status": status, "body": body}
    return _json(body, status)


def _json(body: object, status: int) -> object:
    return Response(
        json.dumps(body),
        status=status,
        headers={"content-type": "application/json; charset=utf-8"},
    )


def _attachment(session: Session, client_ip: str) -> dict[str, object]:
    return {
        "id": session._cf_id,
        "phase": session._cf_phase,
        "name": session._cf_name,
        "reserved": session._cf_reserved,
        "is_new": session._cf_new,
        "race_id": session._cf_race_id,
        "connected_at": session._cf_connected_at,
        "ip": client_ip,
    }


def _safe_key(name: str) -> str:
    from hollow_grid.store import name_key

    return name_key(name)


def _env(env: object, name: str, default: str) -> str:
    try:
        value = getattr(env, name)
    except Exception:
        return default
    if value is None:
        return default
    text = str(value).strip()
    if text in {"", "undefined", "None"}:
        return default
    return text


def _header(headers: object, name: str) -> str:
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    value = getter(name)
    if value is None:
        return ""
    return str(value).strip()


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    return str(value or "")


def _as_str(raw: object) -> str | None:
    if raw is None:
        return None
    to_py = getattr(raw, "to_py", None)
    if to_py is not None:
        raw = to_py()
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw or None
    return str(raw) or None


def _message_text(message: object) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, (bytes, bytearray)):
        return bytes(message).decode("utf-8", errors="replace")
    to_py = getattr(message, "to_py", None)
    if to_py is not None:
        value = to_py()
        if isinstance(value, str):
            return value
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8", errors="replace")
    return str(message)


def _socket_list(ctx: object) -> list[object]:
    raw = ctx.getWebSockets()
    try:
        return list(raw)
    except TypeError:
        length = int(getattr(raw, "length", 0))
        return [raw[index] for index in range(length)]


def _ip_count(sockets: list[object], client_ip: str) -> int:
    count = 0
    for ws in sockets:
        if str(_read_attachment(ws).get("ip") or "") == client_ip:
            count += 1
    return count


def _read_attachment(ws: object) -> dict[str, object]:
    raw = ws.deserializeAttachment()
    if raw is None:
        return {}
    to_py = getattr(raw, "to_py", None)
    if to_py is not None:
        raw = to_py()
    if isinstance(raw, dict):
        return raw
    try:
        return {str(key): raw[key] for key in raw}
    except Exception:
        return {}


def _write_attachment(ws: object, data: dict[str, object]) -> None:
    try:
        from js import Object
        from pyodide.ffi import to_js

        ws.serializeAttachment(to_js(data, dict_converter=Object.fromEntries))
        return
    except Exception:
        ws.serializeAttachment(data)


def _websocket_pair() -> tuple[object, object]:
    from js import WebSocketPair

    pair = WebSocketPair.new()
    values = pair.object_values()
    return values[0], values[1]


def _close(ws: object, code: int, reason: str) -> None:
    try:
        ws.close(code, reason)
    except Exception:
        return


def _send(ws: object, text: str) -> None:
    try:
        ws.send(text)
    except Exception:
        return


async def drain_spawned() -> None:
    current = asyncio.current_task()
    for _ in range(25):
        pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
        if not pending:
            return
        await asyncio.wait(pending, timeout=0.2)
