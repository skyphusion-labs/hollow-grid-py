"""One player WebSocket session: login flow, heartbeat, and command delegation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

import websockets.exceptions

from hollow_grid import event
from hollow_grid.grid.sync import commit_hub_async, merge_hub_on_login_async
from hollow_grid.transport.federation import report_presence
from hollow_grid.transport.gameplay import Gameplay
from hollow_grid.world.model import Player, Room
from hollow_grid.world.races import RACES, race_by_choice

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from hollow_grid.transport.server import WorldServer

CRLF = "\r\n"
WORLD_HEARTBEAT_SEC = 2.0

BANNER = (
    "  +==========================================+"
    + CRLF
    + "  |        V E R D I G R I S   S P O O L        |"
    + CRLF
    + "  |   work the network left half-finished     |"
    + CRLF
    + "  +==========================================+"
)


class Session:
    def __init__(self, ws: ServerConnection, server: WorldServer) -> None:
        self._ws = ws
        self._server = server
        self._world = server.world
        self._store = server.store
        self._hub = server.hub
        self._log = server.log
        self._out: list[str] = []
        self._player: Player | None = None
        self._resolved: set[str] = set()
        self._treat_ready_at: int = 0
        self._gameplay = Gameplay(self)

    def _line(self, text: str) -> None:
        self._out.append(text)

    def _event(self, name: str, payload: object) -> None:
        self._out.append(event.line(name, payload))

    async def _flush(self) -> None:
        if not self._out:
            return
        await self._ws.send("".join(line + CRLF for line in self._out))
        self._out.clear()

    async def _read(self) -> str:
        raw = await self._ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return raw.strip()

    async def run(self) -> None:
        self._line(BANNER)
        self._line("By what name are you known, wanderer?")
        await self._flush()

        name = await self._read()
        if not name:
            return

        sheet, found = self._store.load(name)
        if found:
            self._player = Player.from_sheet(name, sheet, self._world.start().id)
            self._log.info("player resumed name=%s race=%s", name, self._player.race)
            self._line("")
            self._line(
                "Welcome back to the wastes, "
                + name
                + ". (Type 'help' if you need a refresher.) "
                + _resume_line(self._player)
            )
        else:
            if not await self._make_new(name):
                return

        assert self._player is not None
        push = await self._hub.register(self._player)
        await merge_hub_on_login_async(self._server, self._player)
        await self._hub.sync(self._player)
        await report_presence(self._server)
        try:
            await self._hub.broadcast_room(
                self._player.room_id,
                self._player.name + " steps out of the haze.",
                self._player.name,
            )
            self._event(event.WORLD_STATE, self._world.state())
            await self._send_scene()
            await self._flush()

            cmd_q: asyncio.Queue[str | None] = asyncio.Queue()

            async def reader() -> None:
                try:
                    while True:
                        cmd = await self._read()
                        await cmd_q.put(cmd)
                except websockets.exceptions.ConnectionClosedOK:
                    pass
                finally:
                    await cmd_q.put(None)

            reader_task = asyncio.create_task(reader())
            next_tick = asyncio.get_event_loop().time() + WORLD_HEARTBEAT_SEC
            try:
                _wait = object()
                while True:
                    timeout = max(0.0, next_tick - asyncio.get_event_loop().time())
                    cmd: str | None | object = _wait
                    try:
                        cmd = cmd_q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

                    if cmd is _wait:
                        push_task = asyncio.create_task(push.get())
                        cmd_task = asyncio.create_task(cmd_q.get())
                        done, pending = await asyncio.wait(
                            {push_task, cmd_task},
                            timeout=timeout,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await task

                        if cmd_task in done:
                            cmd = cmd_task.result()
                        elif push_task in done:
                            msg = push_task.result()
                            if not msg.endswith(CRLF):
                                msg += CRLF
                            self._out.append(msg)
                            await self._flush()
                            cmd = _wait
                        else:
                            cmd = _wait

                    if cmd is _wait:
                        now = asyncio.get_event_loop().time()
                        if now >= next_tick:
                            self._on_tick()
                            await self._flush()
                            next_tick += WORLD_HEARTBEAT_SEC
                        continue

                    if cmd is None:
                        await self._hub.broadcast_room(
                            self._player.room_id,
                            self._player.name + " flickers out of existence.",
                            self._player.name,
                        )
                        self._log.info("player disconnected name=%s", name)
                        await self._persist_async()
                        return
                    if await self._gameplay.handle(str(cmd)):
                        await self._flush()
                        await self._persist_async()
                        return
                    await self._flush()
            finally:
                reader_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reader_task
        finally:
            self._schedule_persist()
            await self._hub.unregister(self._player.name)

    def _on_tick(self) -> None:
        assert self._player is not None
        self._event(event.WORLD_STATE, self._world.state())
        if self._player.target is not None:
            self._gameplay.combat_round()
        elif self._player.poisoned:
            self._gameplay.poison_tick()
        elif self._player.position == "resting":
            self._gameplay.regen()

    async def _make_new(self, name: str) -> bool:
        self._line("")
        self._line("The Grid does not know the name " + name + ". A new mind, then.")
        race = await self._choose_race()
        if race is None:
            return False
        self._player = Player.new(name, race, self._world.start().id)
        await self._persist_async()
        self._log.info("player created name=%s race=%s", name, race.id)
        self._line("")
        self._line(
            "The Grid takes your name and your shape, "
            + race.name
            + ". Type 'help' if you need a refresher; it is watching what you choose."
        )
        return True

    async def _choose_race(self):
        while True:
            self._line("")
            self._line("Before the Grid will hold your name, choose what you are:")
            for i, race in enumerate(RACES, start=1):
                self._line(f"  {i}) {race.name} -- {race.blurb}")
            self._line("Type a number or a name.")
            await self._flush()
            answer = await self._read()
            chosen = race_by_choice(answer)
            if chosen is not None:
                return chosen
            self._line("The Grid does not recognize that shape.")

    def room(self) -> Room:
        assert self._player is not None
        room = self._world.room(self._player.room_id)
        assert room is not None
        return room

    async def _send_scene(self) -> None:
        assert self._player is not None
        room = self.room()
        self._line("")
        self._line(room.name)
        self._line(room.desc)
        info = room.info(await self._hub.players_in_room(room.id, self._player.name))
        self._event(event.ROOM_INFO, info)
        self._event(event.CHAR_VITALS, self._player.vitals())
        self._event(event.CHAR_AFFECTS, self._player.affects())
        self._event(event.ROOM_ACTIONS, {"actions": await self._gameplay.actions(room)})
        self._gameplay.announce_cache_if_any()

    async def _persist_async(self) -> None:
        if self._player is None:
            return
        with contextlib.suppress(Exception):
            self._store.commit(self._player.name, self._player.sheet())
        await commit_hub_async(self._server, self._player)

    def _schedule_persist(self) -> None:
        """Best-effort hub commit on teardown; never block session close on hub latency."""
        if self._player is None:
            return
        player_name = self._player.name

        async def _run() -> None:
            try:
                await self._persist_async()
            except Exception:
                self._log.exception("disconnect persist failed name=%s", player_name)

        asyncio.create_task(_run(), name="disconnect-persist-" + player_name)


def _resume_line(player: Player) -> str:
    if player.faction in {"Cinder Front", "front"}:
        return "It has not forgotten the coin you took."
    if player.morality >= 25:
        return "It has kept the record of what you chose to be."
    return "You wear the shape of the " + player.race + " still."
