"""HTTP health probes and the /ws player transport."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from hollow_grid.store import CharStore, FileStore
from hollow_grid.transport.hub import Hub
from hollow_grid.transport.session import Session
from hollow_grid.world import DEFAULT_WORLD_NAME, DEFAULT_WORLD_URL, World, build_world

DEFAULT_ADDR = "127.0.0.1"
DEFAULT_PORT = 8791


class WorldServer:
    def __init__(
        self,
        world: World,
        store: CharStore,
        *,
        log: logging.Logger | None = None,
    ) -> None:
        self.world = world
        self.store = store
        self.hub = Hub()
        self.log = log or logging.getLogger("hollow_grid")
        self._sessions = 0
        self._idle = asyncio.Event()
        self._idle.set()

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
        checks = {
            "world": {"ok": world_ok, "latency_ms": 0, "critical": True},
            "grid_hub": {"ok": True, "latency_ms": 0, "critical": False},
        }
        code = 200 if world_ok else 503
        body = {
            "ok": world_ok,
            "ts": int(time.time() * 1000),
            "world": self.world.name,
            "checks": checks,
        }
        return code, body


def _json_response(code: int, body: dict[str, Any]) -> Response:
    reason = "OK" if code == 200 else "Service Unavailable"
    payload = json.dumps(body).encode("utf-8")
    headers = Headers([("Content-Type", "application/json")])
    return Response(code, reason, headers, payload)


async def run_server(
    *,
    host: str = DEFAULT_ADDR,
    port: int = DEFAULT_PORT,
    world_name: str = DEFAULT_WORLD_NAME,
    world_url: str = DEFAULT_WORLD_URL,
    data_dir: str = "data",
) -> WorldServer:
    """Start the world server and return the live instance (runs until cancelled)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("hollow_grid")
    store = FileStore(data_dir)
    world = build_world(world_name, world_url)
    server = WorldServer(world, store, log=log)

    async def handle_ws(ws: ServerConnection) -> None:
        await server.handle_ws(ws)

    async def process_request(_connection: ServerConnection, request: Request) -> Response | None:
        path = request.path.split("?", 1)[0]
        if path == "/health":
            return _json_response(200, server.health_json())
        if path == "/health/deep":
            code, body = server.health_deep_json()
            return _json_response(code, body)
        if path != "/ws":
            headers = Headers([("Content-Type", "text/plain")])
            return Response(404, "Not Found", headers, b"not found\n")
        return None

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
            await server.wait_idle()
            raise

    return server
