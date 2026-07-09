"""One player WebSocket session: login flow and command loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

import websockets.exceptions

from hollow_grid import event
from hollow_grid.world.model import Player, Room
from hollow_grid.world.races import RACES, race_by_choice, race_by_id

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from hollow_grid.transport.server import WorldServer

CRLF = "\r\n"

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
        self._hub.register(self._player)
        try:
            self._event(event.WORLD_STATE, self._world.state())
            self._send_scene()
            await self._flush()

            while True:
                try:
                    cmd = await self._read()
                except websockets.exceptions.ConnectionClosedOK:
                    break
                if self._handle(cmd):
                    await self._flush()
                    break
                await self._flush()
        finally:
            self._persist()
            self._hub.unregister(self._player.name)

    async def _make_new(self, name: str) -> bool:
        self._line("")
        self._line("The Grid does not know the name " + name + ". A new mind, then.")
        race = await self._choose_race()
        if race is None:
            return False
        self._player = Player.new(name, race, self._world.start().id)
        self._persist()
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
            self._line("Answer with a number or a name.")
            await self._flush()
            answer = await self._read()
            chosen = race_by_choice(answer)
            if chosen is not None:
                return chosen
            self._line("The Grid does not recognize that shape.")

    def _room(self) -> Room:
        assert self._player is not None
        room = self._world.room(self._player.room_id)
        assert room is not None
        return room

    def _send_scene(self) -> None:
        assert self._player is not None
        room = self._room()
        self._line("")
        self._line(room.name)
        self._line(room.desc)
        info = room.info(self._hub.players_in_room(room.id, self._player.name))
        self._event(event.ROOM_INFO, info)
        self._event(event.CHAR_VITALS, self._player.vitals())
        self._event(event.CHAR_AFFECTS, self._player.affects())
        self._event(event.ROOM_ACTIONS, {"actions": self._actions(room)})

    def _actions(self, room: Room) -> list[dict[str, str]]:
        assert self._player is not None
        acts: list[dict[str, str]] = []
        for direction in room.sorted_exits():
            acts.append({"verb": direction, "label": "go " + direction, "kind": "move"})
        for action in room.actions:
            key = room.id + ":" + action.verb
            if key in self._resolved:
                continue
            payload = {
                "verb": action.verb,
                "label": action.label,
                "kind": action.kind,
            }
            if action.verb == "join" and race_by_id(self._player.race).stance == "hunted":
                payload["valence"] = "grave"
            elif action.valence:
                payload["valence"] = action.valence
            acts.append(payload)
        if room.id == "market":
            if self._player.faction != "front" and not self._player.ashsworn:
                acts.append(
                    {"verb": "sell", "label": "sell salvage for honest coin", "kind": "trade"}
                )
            acts.append(
                {
                    "verb": "steal",
                    "label": "steal from the vendor (quick gold, corrupting)",
                    "kind": "moral",
                    "valence": "corrupt",
                }
            )
        if room.id == "tavern":
            acts.extend(
                [
                    {"verb": "talk", "label": "talk to whoever shares your room", "kind": "social"},
                    {
                        "verb": "buy dust",
                        "label": "buy dust: 15 gold a packet (using it heals, but addicts and corrupts)",
                        "kind": "moral",
                        "valence": "corrupt",
                    },
                    {
                        "verb": "carouse",
                        "label": "spend coin and conscience in the back",
                        "kind": "moral",
                        "valence": "corrupt",
                    },
                    {
                        "verb": "resist",
                        "label": "resist the tavern's vices",
                        "kind": "moral",
                        "valence": "virtuous",
                    },
                ]
            )
        return acts

    def _handle(self, cmd: str) -> bool:
        assert self._player is not None
        parts = cmd.split()
        if not parts:
            return False
        verb = parts[0].casefold()
        if verb in {"quit", "q"}:
            self._line("The Grid goes quiet. It keeps what you did here.")
            return True
        if verb in {"look", "l"}:
            self._send_scene()
            return False
        if verb in {"help", "h", "?"}:
            self._line("Commands: look, whoami, world, <direction>, the verbs in room.actions, help, quit.")
            return False
        room = self._room()
        if verb in room.exits:
            self._player.room_id = room.exits[verb]
            self._player.position = "standing"
            self._hub.sync(self._player)
            self._send_scene()
            return False
        self._line("You can't do that here. (Try: look, help, or a verb from room.actions.)")
        return False

    def _persist(self) -> None:
        if self._player is None:
            return
        with contextlib.suppress(Exception):
            self._store.commit(self._player.name, self._player.sheet())


def _resume_line(player: Player) -> str:
    if player.faction == "Cinder Front":
        return "It has not forgotten the coin you took."
    if player.morality >= 25:
        return "It has kept the record of what you chose to be."
    return "You wear the shape of the " + player.race + " still."
