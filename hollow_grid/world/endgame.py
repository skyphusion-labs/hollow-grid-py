"""Endgame zones grafted onto the canonical map (src/rooms.ts)."""

from __future__ import annotations

from hollow_grid.world.model import Room
from hollow_grid.world.mobs import new_mob


def endgame_rooms() -> list[Room]:
    return [
        Room(
            id="sump",
            name="The Sump",
            desc=(
                "Ankle-deep in oily runoff that glows a sick green. The walls sweat. Whatever lives down here, "
                "lives hungry. A buckled bulkhead gapes below, and cold air pours up out of it."
            ),
            exits={"up": "tunnels", "down": "floodgate"},
        ),
        Room(
            id="floodgate",
            name="The Breached Floodgate",
            desc=(
                "A bulkhead the size of a truck, buckled open. The sump's runoff pours through it and down into "
                "a drowned cathedral of machines. A stranded operator huddles by a dead console, watching you "
                "with wary hope. (try 'talk')"
            ),
            exits={"up": "sump", "north": "coldrow"},
        ),
        Room(
            id="coldrow",
            name="Cold Storage Row",
            desc=(
                "Aisle after aisle of server racks stand hip-deep in black water, their status lights long dead. "
                "Something pale flickers between them, feeding on whatever current is left."
            ),
            exits={"south": "floodgate", "east": "cooling", "north": "fiber"},
        ),
        Room(
            id="cooling",
            name="The Cooling Pools",
            desc=(
                "Great square pools of coolant gone to scum and rust. A maintenance unit lurches through the "
                "shallows on three working legs, still trying to do its job."
            ),
            exits={"west": "coldrow"},
        ),
        Room(
            id="fiber",
            name="The Fiber Vault",
            desc=(
                "A cathedral nave of severed fiber-optic trunks, each thick as your arm, hanging dead from the "
                "ceiling. This was the spine of the Grid once. Something cold still moves along the cables, where "
                "the light used to."
            ),
            exits={"south": "coldrow", "down": "corelab"},
        ),
        Room(
            id="corelab",
            name="The Core Lab",
            desc=(
                "The drowned heart of the data center. A single black monolith of a server still hums, impossibly, "
                "in the dark, and something has made itself its keeper. It turns to face you. (the Custodian guards it)"
            ),
            exits={"up": "fiber", "west": "archive"},
        ),
        Room(
            id="archive",
            name="The Cold Archive",
            desc=(
                "A sealed vault of tape spools and frozen drives, untouched by the flood. The air is bone-dry and "
                "very cold. Whatever the Grid wanted to keep forever, it kept here."
            ),
            exits={"east": "corelab"},
        ),
        Room(
            id="checkpoint",
            name="The Cinder Front Checkpoint",
            outdoors=True,
            desc=(
                "Sandbags, razor-wire, and a banner stamped with the Front's ash-and-flame mark. An enforcer mans "
                "the barrier, and the road runs north toward the Front's stronghold."
            ),
            exits={"south": "dunes", "north": "gate"},
        ),
        Room(
            id="transit_hub",
            name="The Old Transit Hub",
            outdoors=True,
            desc=(
                "A derelict transit station, platforms cracked, the departure board frozen on a destination that "
                "does not exist anymore. Survivors huddle around a water tap; one of them still works a hand-radio, "
                "sending the looping call you followed here. (try 'shelter')"
            ),
            exits={"north": "scorch_road"},
        ),
        Room(
            id="gate",
            name="The Cinder Gate",
            outdoors=True,
            desc=(
                "A fortress wall of welded scrap and old shipping containers, the ash-and-flame banner snapping "
                "overhead. Troopers watch from firing slits. This is the heart of the Front."
            ),
            exits={"south": "checkpoint", "north": "muster"},
        ),
        Room(
            id="muster",
            name="The Muster Yard",
            outdoors=True,
            desc=(
                "A packed-dirt parade ground where the Front drills, ringed by barracks. Cages line the west wall; "
                "the war room looms to the north."
            ),
            exits={"south": "gate", "west": "cells", "north": "warroom"},
        ),
        Room(
            id="cells",
            name="The Cages",
            desc=(
                "A row of welded cages, packed with elf refugees the Front has rounded up. They press to the bars "
                "when you enter, hope and terror warring in their faces. (try 'free')"
            ),
            exits={"east": "muster"},
        ),
        Room(
            id="warroom",
            name="The War Room",
            desc=(
                "A blast-shelter strung with maps of the wastes, every refugee settlement circled in red. A zealot "
                "poring over the plans. A ladder climbs to the commander's dais above."
            ),
            exits={"south": "muster", "up": "dais"},
        ),
        Room(
            id="dais",
            name="The Ashmonger's Dais",
            outdoors=True,
            desc=(
                "A raised platform of stacked rubble crowned with the Front's banner. The Ashmonger himself stands "
                "here, commander of the Cinder Front, surveying the wastes he means to own."
            ),
            exits={"down": "warroom"},
        ),
    ]


REFUGEE_NAMES = [
    "Sera", "Tomas", "old Wick", "Bex", "Halden", "the Marsh twins", "Ona", "Pavel",
    "little Resh", "Caro", "Dunne", "Yusa", "the smith's boy", "Mira", "Teo", "Nell",
]


def apply_endgame_links(rooms: dict[str, Room]) -> None:
    if tunnels := rooms.get("tunnels"):
        tunnels.exits["down"] = "sump"
        tunnels.desc = (
            "Cramped, dripping, and lit by one surviving strip light. Something skitters in the dark "
            "just past the reach of it. A flooded shaft drops away below."
        )
    if dunes := rooms.get("dunes"):
        dunes.exits["north"] = "checkpoint"
        dunes.desc = (
            "Open desert under a bleached sky, dunes of grey ash rolling to the horizon. A cracked highway "
            "runs east, and the silhouette of a checkpoint stands to the north."
        )
    if scorch := rooms.get("scorch_road"):
        scorch.exits["south"] = "transit_hub"
        scorch.desc = (
            "A ruined stretch of pre-collapse highway, asphalt buckled and tar-black, burned-out hulks lining "
            "the shoulder. A faded sign points south to an old transit hub; that's where the distress call is "
            "coming from."
        )
    rooms["coldrow"].mobs = [new_mob("leech")]
    rooms["checkpoint"].mobs = [new_mob("enforcer")]
    rooms["muster"].mobs = [new_mob("trooper")]
    rooms["warroom"].mobs = [new_mob("zealot")]
    rooms["dais"].mobs = [new_mob("ashmonger")]
    rooms["corelab"].mobs = [new_mob("custodian")]
