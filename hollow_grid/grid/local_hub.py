"""Standalone Grid Hub fallback for federation-shaped calls offline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Trace:
    world: str
    node: str
    kind: str
    text: str
    at: int = 0


@dataclass
class EchoTrace:
    at: int
    kind: str
    text: str


@dataclass
class CharSheet:
    level: int = 1
    xp: int = 0
    gold: int = 0
    faction: str = ""
    morality: int = 0
    title: str = ""
    race: str = ""
    ashsworn: bool = False


@dataclass
class WorldInfo:
    id: str
    url: str
    last_seen: int = 0


@dataclass
class Rescued:
    world: str
    name: str
    saved_by: str
    at: int = 0


@dataclass
class Fallen:
    world: str
    name: str
    room: str
    at: int = 0


@dataclass
class Cast:
    id: int
    world: str
    sender: str
    text: str


@dataclass
class LedgerKind:
    kind: str
    count: int


@dataclass
class PruneResult:
    removed: int = 0


class LocalHub:
    """In-process hub: seeded federation echoes, tide, and gridcast relay."""

    def __init__(self, world_name: str, world_url: str) -> None:
        self.world_name = world_name
        self.world_url = world_url
        self.local: dict[str, list[EchoTrace]] = {}
        self.rescued: list[Rescued] = []
        self.fallen: list[Fallen] = []
        self._tide = 0
        self._casts: list[Cast] = []
        self._cast_id = 0
        self.traces: list[Trace] = [
            Trace("Saltreach", "the drowned pier", "death", "a runner called Mox bled out, cursing the tide.", 0),
            Trace("the Ninth Server", "cell block C", "oath", "someone swore off the dust for the ninth time.", 0),
            Trace("Dustfall", "the long market", "slain", "a trader put down a chrome-jackal with a length of pipe.", 0),
            Trace("Saltreach", "old pier", "ghost", "a footstep where no one walks.", 0),
            Trace("Dustfall", "long market", "passage", "someone passed through without stopping.", 0),
            Trace("the Ninth Server", "cell block C", "recall", "a name spoken twice in error.", 0),
        ]

    def remote(self) -> bool:
        return False

    def record(self, world: str, node: str, kind: str, text: str, at: int = 0) -> None:
        if at == 0:
            at = int(time.time() * 1000)
        self.traces.insert(0, Trace(world, node, kind, text, at))
        if len(self.traces) > 200:
            self.traces = self.traces[:200]

    def record_local(self, node: str, kind: str, text: str) -> None:
        rows = self.local.setdefault(node, [])
        rows.insert(0, EchoTrace(at=int(time.time() * 1000), kind=kind, text=text))
        if len(rows) > 50:
            self.local[node] = rows[:50]

    def local_traces(self, node: str, limit: int) -> list[EchoTrace]:
        rows = self.local.get(node, [])
        if limit <= 0 or limit >= len(rows):
            return list(rows)
        return rows[:limit]

    def recent_across(self, world: str, limit: int) -> list[Trace]:
        out: list[Trace] = []
        for t in self.traces:
            if t.world == world:
                continue
            out.append(t)
            if len(out) >= limit:
                break
        return out

    def all_traces(self, limit: int) -> list[Trace]:
        if limit <= 0 or limit >= len(self.traces):
            return list(self.traces)
        return self.traces[:limit]

    def tide(self) -> int:
        return self._tide

    def shift_tide(self, delta: int) -> int:
        self._tide = max(-100, min(100, self._tide + delta))
        return self._tide

    def load_character(self, name: str) -> tuple[CharSheet, bool]:
        _ = name
        return CharSheet(), False

    def commit_character(self, name: str, sheet: CharSheet) -> None:
        _ = (name, sheet)

    def register(self, world: str, url: str) -> None:
        for i, t in enumerate(self.traces):
            if t.world == world:
                self.traces[i].node = url
                return
        self.traces.insert(
            0,
            Trace(world, url, "register", "a new node joined the network.", int(time.time() * 1000)),
        )

    def list_worlds(self) -> list[WorldInfo]:
        now = int(time.time() * 1000)
        return [
            WorldInfo("Saltreach", "wss://saltreach.example/ws", 0),
            WorldInfo("Dustfall", "wss://dustfall.skyphusion.org/ws", now),
            WorldInfo(self.world_name, self.world_url, now),
        ]

    def report_presence(self, world: str, entries: list[dict[str, str]], at: int) -> None:
        _ = (world, entries, at)

    def presence(self, max_age_ms: int) -> list[dict[str, Any]]:
        _ = max_age_ms
        return []

    def record_rescued(self, world: str, name: str, saved_by: str, at: int = 0) -> None:
        if at == 0:
            at = int(time.time() * 1000)
        self.rescued.insert(0, Rescued(world, name, saved_by, at))
        if len(self.rescued) > 200:
            self.rescued = self.rescued[:200]
        self.record(world, "rescued", "rescue", name + " freed by " + saved_by, at)

    def recent_rescued(self, limit: int) -> list[Rescued]:
        if limit <= 0 or limit >= len(self.rescued):
            return list(self.rescued)
        return self.rescued[:limit]

    def record_fallen(self, world: str, name: str, room: str, at: int = 0) -> None:
        if at == 0:
            at = int(time.time() * 1000)
        self.fallen.insert(0, Fallen(world, name, room, at))
        if len(self.fallen) > 200:
            self.fallen = self.fallen[:200]

    def recent_fallen(self, limit: int) -> list[Fallen]:
        if not self.fallen:
            return []
        if limit <= 0 or limit >= len(self.fallen):
            return list(self.fallen)
        return self.fallen[:limit]

    def grid_cast(self, world: str, sender: str, text: str) -> None:
        self._cast_id += 1
        self._casts.append(Cast(self._cast_id, world, sender, text))

    def casts_since(self, since_id: int, limit: int) -> list[Cast]:
        out = [c for c in self._casts if c.id > since_id]
        if limit > 0:
            out = out[:limit]
        return out

    def ledger_stats(self) -> list[LedgerKind]:
        counts: dict[str, int] = {}
        for t in self.traces:
            counts[t.kind] = counts.get(t.kind, 0) + 1
        return [LedgerKind(kind=k, count=v) for k, v in sorted(counts.items())]

    def prune_ledger_kinds(self, kinds: list[str]) -> PruneResult:
        remove = set(kinds)
        kept: list[Trace] = []
        removed = 0
        for t in self.traces:
            if t.kind in remove:
                removed += 1
            else:
                kept.append(t)
        self.traces = kept
        return PruneResult(removed=removed)
