"""The Hollow Grid structured @event channel (docs/protocol.md section 2)."""

from __future__ import annotations

import json
from typing import Any

PREFIX = "@event "

ROOM_INFO = "room.info"
ROOM_ACTIONS = "room.actions"
CHAR_CREATE = "char.create"
CHAR_VITALS = "char.vitals"
CHAR_AFFECTS = "char.affects"
CHAR_EQUIPMENT = "char.equipment"
CHAR_IDENTITY = "char.identity"
CHAR_DREAM = "char.dream"
CHAR_DIED = "char.died"
COMBAT_START = "combat.start"
COMBAT_ROUND = "combat.round"
COMBAT_END = "combat.end"
WORLD_STATE = "world.state"
WORLD_WAR = "world.war"
GRID_RESCUED = "grid.rescued"
GRID_RESCUED_ROLL = "grid.rescued_roll"
GRID_REDEMPTION = "grid.redemption"
GRID_FALLEN = "grid.fallen"
GRID_REMEMBRANCE = "grid.remembrance"
CHAR_RECKONING = "char.reckoning"
GRID_ECHO = "grid.echo"
GRID_FEDERATION = "grid.federation"
GRID_TRANSMISSION = "grid.transmission"
GRID_WHO = "grid.who"
GRID_WORLDS = "grid.worlds"
GRID_TRAVEL = "grid.travel"
COMM_GRIDCAST = "comm.gridcast"
GRID_LEDGER_STATS = "grid.ledger_stats"
GRID_LEDGER_PRUNED = "grid.ledger_pruned"
COMM_TELL = "comm.tell"
COMM_YELL = "comm.yell"
CHAR_FORGIVEN = "char.forgiven"
CHAR_TREATED = "char.treated"
PLAYER_READ = "player.read"
SERVER_ANNOUNCE = "server.announce"
NODE_CACHE = "node.cache"
GRID_INSCRIBED = "grid.inscribed"


def line(name: str, payload: Any) -> str:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return f"{PREFIX}{name} {body}"
