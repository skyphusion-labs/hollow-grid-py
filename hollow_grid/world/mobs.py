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
    room: str = ""
    respawn_ms: int = 0


MOB_CATALOG: dict[str, MobTemplate] = {
    "rat": MobTemplate(
        id="rat",
        name="a glow-rat",
        desc="A bloated rodent, fur matted and faintly luminous with absorbed rads.",
        max_hp=12,
        damage=4,
        room="tunnels",
        respawn_ms=20_000,
    ),
    "scav": MobTemplate(
        id="scav",
        name="a feral scavenger",
        desc="A wiry figure in stitched rags, eyeing your gear like it's already theirs.",
        max_hp=26,
        damage=6,
    ),
    "drone": MobTemplate(
        id="drone",
        name="a malfunctioning drone",
        desc="A dented quadcopter sparking at the rotors, its targeting laser twitching.",
        max_hp=18,
        damage=5,
    ),
    "scorpion": MobTemplate(
        id="scorpion",
        name="a rad-scorpion",
        desc="A dog-sized arthropod of chitin and rust, tail arched and dripping venom.",
        max_hp=10,
        damage=5,
    ),
    "raider": MobTemplate(
        id="raider",
        name="a wastes raider",
        desc=(
            "A scarred figure wrapped in sun-bleached rags and scavenged plate, hefting a length "
            "of rebar and grinning at the easy mark you make."
        ),
        max_hp=22,
        damage=6,
        room="scorch_road",
        respawn_ms=40_000,
    ),
    "warden": MobTemplate(
        id="warden",
        name="the warden",
        desc=(
            "A chrome-masked jailer, broad as a doorway, the keys to the holding-pit cage "
            "hanging from their belt."
        ),
        max_hp=18,
        damage=5,
        room="holding_pit",
        respawn_ms=60_000,
    ),
    "leech": MobTemplate(
        id="leech",
        name="a data-leech",
        desc=(
            "A pale, boneless thing clamped to a live rack, swollen with stolen current. "
            "It turns toward your warmth."
        ),
        max_hp=18,
        damage=5,
        room="coldrow",
        respawn_ms=30_000,
    ),
    "enforcer": MobTemplate(
        id="enforcer",
        name="a Cinder Front enforcer",
        desc=(
            "A heavyset Front soldier in ash-grey plate -- more bully than soldier, "
            "but the gun on their hip is real enough."
        ),
        max_hp=34,
        damage=7,
        room="checkpoint",
        respawn_ms=90_000,
    ),
    "trooper": MobTemplate(
        id="trooper",
        name="a Cinder Front trooper",
        desc=(
            "A drilled Front soldier in matched ash-grey gear, moving like someone "
            "who's done this killing before."
        ),
        max_hp=30,
        damage=6,
        room="muster",
        respawn_ms=60_000,
    ),
    "zealot": MobTemplate(
        id="zealot",
        name="a Front zealot",
        desc=(
            "A true believer with the ash-and-flame branded into their own skin, eyes bright "
            "with the cause and nothing behind them."
        ),
        max_hp=36,
        damage=7,
        room="warroom",
        respawn_ms=75_000,
    ),
    "ashmonger": MobTemplate(
        id="ashmonger",
        name="the Ashmonger",
        desc=(
            "Commander of the Cinder Front: a slab-shouldered butcher in scorched plate, leaning "
            "on a cleaver as long as your leg, smiling like he's already won."
        ),
        max_hp=100,
        damage=10,
        room="dais",
        respawn_ms=180_000,
    ),
    "custodian": MobTemplate(
        id="custodian",
        name="the Custodian",
        desc=(
            "A hunched automaton of rusted chrome, still guarding the drowned core with a shard "
            "of light clutched in its claws."
        ),
        max_hp=45,
        damage=8,
        room="corelab",
        respawn_ms=120_000,
    ),
}


def respawn_for(template_id: str) -> tuple[str, int] | None:
    t = MOB_CATALOG.get(template_id)
    if t is None or t.respawn_ms <= 0 or not t.room:
        return None
    return t.room, t.respawn_ms


def new_mob(template_id: str) -> Mob:
    t = MOB_CATALOG[template_id]
    return Mob(id=t.id, name=t.name, desc=t.desc, max_hp=t.max_hp, hp=t.max_hp, damage=t.damage)
