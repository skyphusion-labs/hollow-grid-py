"""Multiplayer presence registry and push routing."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hollow_grid import event
from hollow_grid.world.brand import brand

if TYPE_CHECKING:
    from hollow_grid.world.model import Player

CRLF = "\r\n"
PUSH_RELIABLE_MS = 5.0
_log = logging.getLogger("hollow_grid")


@dataclass
class LivePlayer:
    name: str
    room: str
    title: str
    faction: str
    race: str
    ashsworn: bool
    morality: int
    hp: int
    max_hp: int
    push: asyncio.Queue[str]
    reply_to: str = ""
    plr: Player | None = None


@dataclass
class Hub:
    _players: dict[str, LivePlayer] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def register(self, player: Player) -> asyncio.Queue[str]:
        ch: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        lp = LivePlayer(
            name=player.name,
            room=player.room_id,
            title=player.title,
            faction=player.faction,
            race=player.race,
            ashsworn=player.ashsworn,
            morality=player.morality,
            hp=player.hp,
            max_hp=player.max_hp,
            push=ch,
            plr=player,
        )
        async with self._lock:
            self._players[player.name] = lp
        return ch

    async def unregister(self, name: str) -> None:
        async with self._lock:
            self._players.pop(name, None)

    async def sync(self, player: Player) -> None:
        async with self._lock:
            lp = self._players.get(player.name)
            if lp is None:
                return
            lp.room = player.room_id
            lp.title = player.title
            lp.faction = player.faction
            lp.race = player.race
            lp.ashsworn = player.ashsworn
            lp.morality = player.morality
            lp.hp = player.hp
            lp.max_hp = player.max_hp

    async def set_reply_to(self, name: str, from_name: str) -> None:
        async with self._lock:
            lp = self._players.get(name)
            if lp is not None:
                lp.reply_to = from_name

    async def reply_to(self, name: str) -> str:
        async with self._lock:
            lp = self._players.get(name)
            return lp.reply_to if lp is not None else ""

    async def find(self, name: str) -> LivePlayer | None:
        async with self._lock:
            if lp := self._players.get(name):
                return lp
            lower = name.strip().casefold()
            for n, lp in self._players.items():
                if n.casefold() == lower:
                    return lp
        return None

    async def find_prefix(self, prefix: str) -> LivePlayer | None:
        prefix = prefix.strip().casefold()
        async with self._lock:
            for name, lp in self._players.items():
                if name.casefold().startswith(prefix):
                    return lp
        return None

    async def players_in_room(self, room_id: str, except_name: str = "") -> list[dict[str, str]]:
        async with self._lock:
            out: list[dict[str, str]] = []
            for name, lp in self._players.items():
                if name == except_name or lp.room != room_id:
                    continue
                out.append({"name": name, "standing": _brand_live(lp)})
            return out

    async def all_players(self) -> list[LivePlayer]:
        async with self._lock:
            return list(self._players.values())

    async def push(self, name: str, text: str) -> None:
        lp = await self.find(name)
        if lp is None:
            return
        _push_best_effort(lp, text)

    async def push_reliable(self, name: str, text: str) -> None:
        lp = await self.find(name)
        if lp is None:
            return
        await _push_reliable(lp, text)

    async def push_reliable_room(self, room: str, text: str, skip: str) -> None:
        async with self._lock:
            targets = [lp for n, lp in self._players.items() if lp.room == room and n != skip]
        for lp in targets:
            await _push_reliable(lp, text)

    async def broadcast_room(self, room: str, text: str, skip: str = "") -> None:
        async with self._lock:
            targets = [lp for n, lp in self._players.items() if lp.room == room and n != skip]
        for lp in targets:
            _push_best_effort(lp, text, player=lp.name)

    async def broadcast_all(self, text: str) -> None:
        async with self._lock:
            targets = list(self._players.values())
        for lp in targets:
            _push_best_effort(lp, text, player=lp.name)

    async def broadcast_room_except(self, room: str, text: str, skip1: str, skip2: str = "") -> None:
        async with self._lock:
            targets = [
                lp for n, lp in self._players.items()
                if lp.room == room and n != skip1 and n != skip2
            ]
        for lp in targets:
            _push_best_effort(lp, text, player=lp.name)

    async def broadcast_all_except(self, text: str, skip: str) -> None:
        async with self._lock:
            targets = [lp for n, lp in self._players.items() if n != skip]
        for lp in targets:
            _push_best_effort(lp, text, player=lp.name)

    async def push_event(self, name: str, ev_name: str, payload: Any) -> None:
        await self.push(name, event.line(ev_name, payload) + CRLF)

    async def push_event_reliable(self, name: str, ev_name: str, payload: Any) -> None:
        await self.push_reliable(name, event.line(ev_name, payload) + CRLF)


def _brand_live(lp: LivePlayer) -> str:
    from hollow_grid.world.model import Player

    p = Player(
        name=lp.name,
        race=lp.race,
        room_id=lp.room,
        hp=lp.hp,
        max_hp=lp.max_hp,
        faction=lp.faction,
        morality=lp.morality,
        ashsworn=lp.ashsworn,
    )
    return brand(p)


def _push_best_effort(lp: LivePlayer, text: str, *, player: str = "") -> None:
    try:
        lp.push.put_nowait(text)
    except asyncio.QueueFull:
        pass
    except Exception as exc:
        _log.warning("broadcast push failed player=%s err=%s", player or lp.name, exc)


async def _push_reliable(lp: LivePlayer, text: str) -> None:
    deadline = asyncio.get_event_loop().time() + PUSH_RELIABLE_MS
    while True:
        try:
            lp.push.put_nowait(text)
            return
        except asyncio.QueueFull:
            if asyncio.get_event_loop().time() >= deadline:
                return
            await asyncio.sleep(0.01)
