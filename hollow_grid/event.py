"""The Hollow Grid structured @event channel (docs/protocol.md section 2)."""

from __future__ import annotations

import json
from typing import Any

PREFIX = "@event "

# Canonical event names (growing subset of the protocol vocabulary).
ROOM_INFO = "room.info"
ROOM_ACTIONS = "room.actions"
CHAR_VITALS = "char.vitals"
CHAR_AFFECTS = "char.affects"
WORLD_STATE = "world.state"


def line(name: str, payload: Any) -> str:
    """Format one @event line (no trailing CRLF; transport adds it)."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return f"{PREFIX}{name} {body}"
