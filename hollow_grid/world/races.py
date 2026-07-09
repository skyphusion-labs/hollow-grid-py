"""Canonical races (the-hollow-grid src/races.ts, hollow-grid-go internal/world/races.go)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ability:
    verb: str
    name: str
    desc: str
    cooldown_ms: int


@dataclass(frozen=True)
class Race:
    id: str
    name: str
    blurb: str
    stance: str
    hp_mod: int = 0
    damage: int = 0
    armor: int = 0
    regen: int = 0
    poison_immune: bool = False
    trait: str = ""
    ability: Ability | None = None


RACES: list[Race] = [
    Race(
        id="human",
        name="Human",
        blurb="the Registered -- the Front's idea of a real person",
        stance="accepted",
        trait="Unmarked. The registry, the vendors, and the checkpoints treat you as a person by default.",
        ability=Ability("requisition", "Requisition", "call in a registry payout; the system pays its own", 180_000),
    ),
    Race(
        id="elf",
        name="Elf",
        blurb="the Unregistered -- the people the Cinder Front hunts",
        stance="hunted",
        regen=1,
        trait="Quick and resilient; you recover a little faster. The Front's cages, rallies, and checkpoints are about you.",
        ability=Ability("vanish", "Vanish", "slip the net: break off any fight and disappear", 45_000),
    ),
    Race(
        id="revenant",
        name="Revenant",
        blurb="a mind the network kept after the body failed",
        stance="hunted",
        poison_immune=True,
        trait="No flesh to rot: poison and the pox cannot touch you. The Front calls you an abomination, not a citizen.",
        ability=Ability("commune", "Commune", "reach into the dead Grid for its memory and a little of its cold life", 120_000),
    ),
    Race(
        id="ghoul",
        name="Ghoul",
        blurb="rad-scoured human, hard to kill",
        stance="tolerated",
        hp_mod=10,
        trait="You carry more hit points than flesh should. The Front works you, and never lets you forget you are not 'real'.",
        ability=Ability("regenerate", "Regenerate", "rad-scoured flesh knits itself back: a heavy self-heal", 120_000),
    ),
    Race(
        id="chromed",
        name="Chromed",
        blurb="flesh half-replaced with salvage augments",
        stance="tolerated",
        damage=1,
        armor=1,
        trait="Chrome under the skin: a little more bite, a little more plate. The Front's muscle is chromed too, until you go too far.",
        ability=Ability("overclock", "Overclock", "vent your augments past every safety into one devastating strike", 30_000),
    ),
    Race(
        id="dustkin",
        name="Dustkin",
        blurb="born to the open pan, owing the registry nothing",
        stance="hunted",
        regen=2,
        trait="At home where others die: you heal faster out in the world. The Front hunts you as a vagrant.",
        ability=Ability("forage", "Forage", "scavenge the open wastes for supplies (outdoors only)", 90_000),
    ),
    Race(
        id="vatborn",
        name="Vatborn",
        blurb="grown, not born, in the old fabrication vats",
        stance="hunted",
        hp_mod=5,
        trait="Printed sturdy: a little extra frame. No lineage the Front recognizes, so they call you property.",
        ability=Ability("fabricate", "Fabricate", "print a field stim from raw salvage", 120_000),
    ),
]


def race_by_choice(answer: str) -> Race | None:
    answer = answer.strip()
    if answer.isdigit():
        n = int(answer)
        if 1 <= n <= len(RACES):
            return RACES[n - 1]
        return None
    low = answer.casefold()
    for race in RACES:
        if race.id.casefold() == low or race.name.casefold() == low:
            return race
    return None


def race_by_id(race_id: str) -> Race:
    low = race_id.casefold()
    for race in RACES:
        if race.id.casefold() == low:
            return race
    return RACES[0]
