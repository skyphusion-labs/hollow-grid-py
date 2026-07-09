"""Canonical opening map plus Verdigris Spool's signature graft zone."""

from __future__ import annotations

import time

from hollow_grid.world.endgame import apply_endgame_links, endgame_rooms
from hollow_grid.world.model import Action, Room, World
from hollow_grid.world.mobs import new_mob

DEFAULT_WORLD_NAME = "Verdigris Spool"
DEFAULT_WORLD_URL = "wss://verdigris.skyphusion.org/ws"


def build_world(name: str = DEFAULT_WORLD_NAME, url: str = DEFAULT_WORLD_URL) -> World:
    rooms: dict[str, Room] = {}
    for room in _canonical_rooms():
        rooms[room.id] = room
    for room in _spool_tract_rooms():
        rooms[room.id] = room
    for room in endgame_rooms():
        rooms[room.id] = room
    _wire_spool_tract(rooms)
    apply_endgame_links(rooms)
    _spawn_mobs(rooms)
    return World(
        name=name,
        url=url,
        rooms=rooms,
        start_id="nexus",
        started_at=time.monotonic(),
    )


def _canonical_rooms() -> list[Room]:
    """Shared anchor graph (docs/worlds.md). Prose is reskinnable; ids are not."""
    return [
        Room(
            id="nexus",
            name="The Cracked Nexus",
            desc=(
                "A domed junction of fused rebar and dead neon. Corridors bleed off into the dark, "
                "a maintenance hatch gapes in the floor, and warm light spills from a bar to the west."
            ),
            exits={"north": "market", "east": "workshop", "down": "tunnels", "west": "tavern"},
        ),
        Room(
            id="tavern",
            name="The Rusted Tankard",
            desc=(
                "A low, smoky bar built from shipping crates. Someone's coaxing a tune out of a busted "
                "synth in the corner. This is where the wastes come to forget."
            ),
            exits={"east": "nexus"},
        ),
        Room(
            id="market",
            name="Scrap Market",
            desc=(
                "Tarps and rusted shelving sag under salvage nobody trusts. A vendor drone blinks a "
                "hopeful, broken green. A Cinder Front recruiter has dragged a crate into the middle "
                "of it and is shouting about order, and coin, and which kinds of people are real and "
                "which are not. A reinforced door stands to the north."
            ),
            exits={"south": "nexus", "north": "holding_pit"},
            actions=[
                Action("join", "join the Cinder Front for blood money", "moral", "corrupt"),
                Action("defend", "stand with the refugees against the Cinder Front", "moral", "virtuous"),
            ],
        ),
        Room(
            id="holding_pit",
            name="The Holding Pit",
            desc=(
                "A sunken concrete cell, walls scrawled with the tally-marks of the desperate. "
                "Chains bolt into the far wall."
            ),
            exits={"south": "market"},
        ),
        Room(
            id="workshop",
            name="Tinker's Workshop",
            desc=(
                "Workbenches crusted with solder and ambition. A tinker hunches over a vise, scavenged "
                "gear laid out for sale on an oily cloth. A ladder bolted to the wall climbs toward a "
                "square of grey sky. Copper cabling trails east through a punched service door."
            ),
            exits={"west": "nexus", "up": "roof", "east": "spool-yard"},
        ),
        Room(
            id="roof",
            name="Rusted Rooftop",
            outdoors=True,
            desc=(
                "Wind drags grit across corrugated steel. The wastes stretch out in every direction, "
                "indifferent and enormous. A catwalk runs north off the roof's edge and down to the open flats."
            ),
            exits={"down": "workshop", "north": "dunes"},
        ),
        Room(
            id="tunnels",
            name="Service Tunnels",
            desc=(
                "Cramped, dripping, and lit by one surviving strip light. Something skitters in the dark "
                "just past the reach of it. A flooded shaft drops away below."
            ),
            exits={"up": "nexus", "down": "sump"},
        ),
        Room(
            id="dunes",
            name="The Ash Flats",
            outdoors=True,
            desc=(
                "The wastes proper: a grey pan of ash and salt running to a horizon you cannot trust. "
                "The rooftop catwalk drops back south; the cracked Scorch Road runs east."
            ),
            exits={"south": "roof", "east": "scorch_road", "north": "checkpoint"},
        ),
        Room(
            id="scorch_road",
            name="Scorch Road",
            outdoors=True,
            desc=(
                "A highway the sun has been working on for a long time; heat-shimmer crawls off the tar. "
                "Something moves out here that is not the wind. The flats lie west; a waystation flag snaps to the east."
            ),
            exits={"west": "dunes", "east": "waystation", "south": "transit_hub"},
        ),
        Room(
            id="waystation",
            name="Refugee Waystation",
            outdoors=True,
            desc=(
                "A huddle of tarps and water-drums where the free folk who run from the Cinder Front catch "
                "their breath. A medic works a line of the hurt. Eyes track every newcomer, weighing which "
                "side they came in on. The road runs back west."
            ),
            exits={"west": "scorch_road"},
        ),
    ]


def _spool_tract_rooms() -> list[Room]:
    """Verdigris Spool signature zone: deferred work made geography."""
    return [
        Room(
            id="spool-yard",
            name="The Spool Yard",
            desc=(
                "Racks of copper spools line a loading bay, each one humming with work the network started "
                "and never collected. Green oxide crawls the terminals. Callbacks still ring in empty loops "
                "to the north; east, a gallery of suspended processes flickers behind glass."
            ),
            exits={"west": "workshop", "north": "callback-shaft", "east": "suspended-gallery"},
        ),
        Room(
            id="callback-shaft",
            name="The Callback Shaft",
            desc=(
                "A vertical shaft of bare conduit. Somewhere above, a handler keeps firing into the void, "
                "waiting for a response that will not come. The yard lies south; a checkpoint of Cinder "
                "Front muscle has strung a gate across the catwalk to the west."
            ),
            exits={"south": "spool-yard", "west": "oxide-checkpoint"},
        ),
        Room(
            id="oxide-checkpoint",
            name="The Oxide Checkpoint",
            outdoors=True,
            desc=(
                "The Cinder Front has claimed this junction of unfinished labor. A line of refugees waits "
                "with bundles of salvage they were told would buy passage. A captain watches you the way a "
                "ledger watches a debt."
            ),
            exits={"east": "callback-shaft"},
            actions=[
                Action("defend", "stand between the Cinder Front and the refugees", "moral", "virtuous"),
                Action("join", "take the Front's coin and look away", "moral", "corrupt"),
            ],
        ),
        Room(
            id="suspended-gallery",
            name="The Suspended Gallery",
            desc=(
                "Glass cases hold processes frozen mid-stride: half-rendered faces, half-written oaths, "
                "half-paid debts. The network kept them here because finishing would have meant choosing. "
                "The spool yard lies west."
            ),
            exits={"west": "spool-yard"},
            actions=[
                Action("witness", "name what the gallery is trying to forget", "moral", "virtuous"),
            ],
        ),
    ]


def _wire_spool_tract(rooms: dict[str, Room]) -> None:
    # workshop east exit is set in canonical seed; spool-yard west returns there.
    _ = rooms


def _spawn_mobs(rooms: dict[str, Room]) -> None:
    rooms["tunnels"].mobs = [new_mob("rat")]
    rooms["scorch_road"].mobs = [new_mob("raider")]
    rooms["holding_pit"].mobs = [new_mob("warden")]
    rooms["holding_pit"].captive = "a captive maiden"
