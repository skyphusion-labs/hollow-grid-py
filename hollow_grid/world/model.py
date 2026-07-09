"""World model: rooms, players, and @event payloads."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hollow_grid.world.mobs import Mob, MobRef, new_mob, respawn_for
from hollow_grid.world.races import Race, race_by_id

STARTER_WEAPON = "shiv"
BASE_MAX_HP = 30
HP_PER_LEVEL = 10

WORLD_TICK_SEC = 2.0
PHASE_EVERY_TICKS = 30
WEATHER_EVERY_TICKS = 9

PHASES = ("day", "dusk", "night", "dawn")
WEATHERS = (
    "clear",
    "a haze of grid-static",
    "acid drizzle",
    "a dust storm",
    "an unnatural stillness",
)


@dataclass
class Action:
    verb: str
    label: str
    kind: str
    valence: str = ""


@dataclass
class Room:
    id: str
    name: str
    desc: str
    exits: dict[str, str] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    outdoors: bool = False
    mobs: list[Mob] = field(default_factory=list)
    captive: str = ""

    def sorted_exits(self) -> list[str]:
        return sorted(self.exits)

    def info(self, players: list[dict[str, str]] | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "exits": self.sorted_exits(),
            "mobs": [{"id": m.id, "name": m.name} for m in self.mobs],
            "items": [],
            "players": players or [],
        }

    def mob(self, arg: str) -> Mob | None:
        arg = arg.strip().casefold()
        if not arg:
            return None
        for mob in self.mobs:
            if mob.id == arg or arg in mob.id.casefold() or arg in mob.name.casefold():
                return mob
        return None


@dataclass
class CharSheet:
    level: int = 1
    xp: int = 0
    gold: int = 20
    faction: str = "none"
    morality: int = 0
    title: str = ""
    race: str = "human"
    ashsworn: bool = False
    strayed: bool = False
    redeemed: bool = False
    resisted: bool = False


def max_hp_for(level: int, hp_mod: int) -> int:
    if level < 1:
        level = 1
    return BASE_MAX_HP + (level - 1) * HP_PER_LEVEL + hp_mod


@dataclass
class Player:
    name: str
    race: str
    room_id: str
    hp: int
    max_hp: int
    level: int = 1
    xp: int = 0
    gold: int = 20
    morality: int = 0
    faction: str = "none"
    title: str = ""
    ashsworn: bool = False
    strayed: bool = False
    redeemed: bool = False
    resisted: bool = False
    inventory: list[str] = field(default_factory=list)
    equipment: dict[str, str] = field(default_factory=dict)
    position: str = "standing"
    addiction: int = 0
    poisoned: bool = False
    target: Mob | None = None
    trait_ready_at: float = 0.0

    @classmethod
    def new(cls, name: str, race: Race, start_room: str) -> Player:
        mh = max_hp_for(1, race.hp_mod)
        return cls(
            name=name,
            race=race.id,
            room_id=start_room,
            hp=mh,
            max_hp=mh,
            gold=20,
            faction="none",
            inventory=[STARTER_WEAPON],
        )

    @classmethod
    def from_sheet(cls, name: str, sheet: CharSheet, start_room: str) -> Player:
        race = race_by_id(sheet.race)
        level = max(sheet.level, 1)
        mh = max_hp_for(level, race.hp_mod)
        faction = sheet.faction or "none"
        return cls(
            name=name,
            race=sheet.race,
            room_id=start_room,
            hp=mh,
            max_hp=mh,
            level=level,
            xp=sheet.xp,
            gold=sheet.gold,
            morality=sheet.morality,
            faction=faction,
            title=sheet.title,
            ashsworn=sheet.ashsworn,
            strayed=sheet.strayed,
            redeemed=sheet.redeemed,
            resisted=sheet.resisted,
            inventory=[STARTER_WEAPON],
        )

    def sheet(self) -> CharSheet:
        return CharSheet(
            level=self.level,
            xp=self.xp,
            gold=self.gold,
            faction=self.faction,
            morality=self.morality,
            title=self.title,
            race=self.race,
            ashsworn=self.ashsworn,
            strayed=self.strayed,
            redeemed=self.redeemed,
            resisted=self.resisted,
        )

    def vitals(self) -> dict[str, Any]:
        pos = self.position or "standing"
        if self.target is not None:
            pos = "fighting"
        return {
            "hp": self.hp,
            "maxHp": self.max_hp,
            "level": self.level,
            "xp": self.xp,
            "gold": self.gold,
            "room": self.room_id,
            "inCombat": self.target is not None,
            "poisoned": self.poisoned,
            "position": pos,
        }

    def affects(self) -> dict[str, Any]:
        return {
            "morality": self.morality,
            "addiction": self.addiction,
            "faction": self.faction,
            "resisted": self.resisted,
            "race": self.race,
            "ashsworn": self.ashsworn,
        }


@dataclass
class World:
    name: str
    url: str
    rooms: dict[str, Room]
    start_id: str
    started_at: float

    def start(self) -> Room:
        return self.rooms[self.start_id]

    def room(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)

    def remove_mob(self, room_id: str, mob: Mob) -> None:
        room = self.room(room_id)
        if room is None or mob is None:
            return
        for i, mm in enumerate(room.mobs):
            if mm is mob:
                del room.mobs[i]
                return

    def has_mob(self, template_id: str) -> bool:
        info = respawn_for(template_id)
        if info is None:
            return False
        room_id, _ = info
        room = self.room(room_id)
        if room is None:
            return False
        return any(m.id == template_id for m in room.mobs)

    def spawn_mob(self, template_id: str) -> Mob | None:
        info = respawn_for(template_id)
        if info is None:
            return None
        room_id, _ = info
        room = self.room(room_id)
        if room is None:
            return None
        for m in room.mobs:
            if m.id == template_id:
                return m
        mob = new_mob(template_id)
        room.mobs.append(mob)
        return mob

    def state(self) -> dict[str, Any]:
        tick = int((time.monotonic() - self.started_at) / WORLD_TICK_SEC)
        return {
            "tick": tick,
            "phase": PHASES[(tick // PHASE_EVERY_TICKS) % len(PHASES)],
            "weather": WEATHERS[(tick // WEATHER_EVERY_TICKS) % len(WEATHERS)],
        }
