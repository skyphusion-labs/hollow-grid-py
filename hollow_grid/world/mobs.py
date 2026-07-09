"""Live creatures and mob references for room.info."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MobRef:
    id: str
    name: str


@dataclass
class Mob:
    id: str
    name: str
    desc: str
    max_hp: int
    hp: int
    damage: int

    def ref(self) -> MobRef:
        return MobRef(id=self.id, name=self.name)


@dataclass(frozen=True)
class MobTemplate:
    id: str
    name: str
    desc: str
    max_hp: int
    damage: int


MOB_CATALOG: dict[str, MobTemplate] = {
    "rat": MobTemplate(
        id="rat",
        name="a glow-rat",
        desc="A bloated rodent, fur matted and faintly luminous with absorbed rads.",
        max_hp=12,
        damage=4,
    ),
    "raider": MobTemplate(
        id="raider",
        name="a wastes raider",
        desc="A scarred figure wrapped in sun-bleached rags and scavenged plate, hefting a length of rebar and grinning at the easy mark you make.",
        max_hp=22,
        damage=6,
    ),
    "warden": MobTemplate(
        id="warden",
        name="the warden",
        desc="A chrome-masked jailer, broad as a doorway, the keys to the holding-pit cage hanging from their belt.",
        max_hp=18,
        damage=5,
    ),
}


def new_mob(template_id: str) -> Mob:
    t = MOB_CATALOG[template_id]
    return Mob(id=t.id, name=t.name, desc=t.desc, max_hp=t.max_hp, hp=t.max_hp, damage=t.damage)
