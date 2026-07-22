"""HTTP JSON-RPC client for the shared Grid Hub (mirrors hollow-grid-go remote.go)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from hollow_grid.grid.local_hub import (
    Cast,
    CharSheet,
    Fallen,
    LedgerKind,
    Presence,
    PruneResult,
    Rescued,
    Trace,
    WorldInfo,
)

_RPC_TIMEOUT_SEC = 2


class GridHubError(Exception):
    """Grid Hub RPC failed; federation must never block play."""


class RemoteHub:
    """Calls a Grid Hub over HTTP JSON-RPC (POST /rpc)."""

    def __init__(
        self,
        hub_url: str,
        token: str = "",
        world_name: str = "",
        world_url: str = "",
        world_key: str = "",
    ) -> None:
        self.hub_url = hub_url.strip().rstrip("/")
        self.token = token.strip()
        self.world_name = world_name.strip()
        self.world_url = world_url
        self.world_key = world_key.strip()

    def remote(self) -> bool:
        return True

    def _set_world_headers(self, req: urllib.request.Request, world: str) -> None:
        if world:
            req.add_header("X-Grid-World", world)
        if self.world_key:
            req.add_header("X-Grid-World-Key", self.world_key)

    def _call(
        self,
        method: str,
        params: list[Any],
        out: type | None = None,
        *,
        auth_world: str = "",
    ) -> Any:
        body = json.dumps({"method": method, "params": params}).encode("utf-8")
        req = urllib.request.Request(
            self.hub_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "hollow-grid-py/0.1.0",
            },
        )
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        self._set_world_headers(req, auth_world)
        try:
            with urllib.request.urlopen(req, timeout=_RPC_TIMEOUT_SEC) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GridHubError(f"grid rpc {method}: {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise GridHubError(f"grid rpc {method}: {exc.reason}") from exc

        try:
            wrap = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GridHubError(f"grid rpc {method}: invalid json") from exc
        if not wrap.get("ok"):
            err = str(wrap.get("error") or "rpc failed")
            raise GridHubError(f"grid rpc {method}: {err}")

        result = wrap.get("result")
        if out is None:
            return result
        if result is None:
            return None
        if out is int:
            return int(result)
        if out is PruneResult:
            if isinstance(result, dict):
                return PruneResult(removed=int(result.get("removed", 0)))
            return PruneResult()
        if out is list:
            return result
        return result

    def ping(self) -> None:
        self.tide()

    def record(self, world: str, node: str, kind: str, text: str, at: int = 0) -> None:
        self._call("record", [world, node, kind, text, at])

    def recent_across(self, world: str, limit: int) -> list[Trace]:
        raw = self._call("recentAcross", [world, limit], list)
        if not isinstance(raw, list):
            return []
        return [_trace_row(row) for row in raw if isinstance(row, dict)]

    def tide(self) -> int:
        value = self._call("tide", [], int)
        return int(value) if value is not None else 0

    def shift_tide(self, delta: int) -> int:
        value = self._call("shiftTide", [delta], int)
        return int(value) if value is not None else 0

    def load_character(self, name: str) -> tuple[CharSheet, bool]:
        raw = self._call(
            "loadCharacter",
            [name, self.world_name],
            auth_world=self.world_name,
        )
        if not isinstance(raw, dict):
            return CharSheet(), False
        sheet = _char_sheet_row(raw)
        found = (
            sheet.race != ""
            or sheet.level > 1
            or sheet.xp > 0
            or sheet.faction != ""
            or sheet.morality != 0
        )
        return sheet, found

    def commit_character(self, name: str, sheet: CharSheet) -> None:
        self._call(
            "commitCharacter",
            [name, self.world_name, _sheet_row(sheet)],
            auth_world=self.world_name,
        )

    def claim_character_lease(self, name: str) -> None:
        self._call(
            "claimCharacterLease",
            [name, self.world_name],
            auth_world=self.world_name,
        )

    def register(self, world: str, url: str) -> None:
        self._call("register", [world, url], auth_world=world)

    def list_worlds(self) -> list[WorldInfo]:
        raw = self._call("listWorlds", [])
        if not isinstance(raw, list):
            return []
        return [_world_row(row) for row in raw if isinstance(row, dict)]

    def grid_cast(self, world: str, sender: str, text: str) -> None:
        self._call("gridcast", [world, sender, text])

    def casts_since(self, since_id: int, limit: int) -> list[Cast]:
        raw = self._call("castsSince", [since_id, limit], list)
        if not isinstance(raw, list):
            return []
        return [_cast_row(row) for row in raw if isinstance(row, dict)]

    def ledger_stats(self) -> list[LedgerKind]:
        raw = self._call("ledgerStats", [])
        if not isinstance(raw, list):
            return []
        return [
            LedgerKind(kind=str(row.get("kind", "")), count=int(row.get("count", 0)))
            for row in raw
            if isinstance(row, dict)
        ]

    def prune_ledger_kinds(self, kinds: list[str]) -> PruneResult:
        raw = self._call("pruneLedgerKinds", [kinds], PruneResult)
        if isinstance(raw, PruneResult):
            return raw
        if isinstance(raw, dict):
            return PruneResult(removed=int(raw.get("removed", 0)))
        return PruneResult()

    def report_presence(self, world: str, entries: list[dict[str, str]], at: int) -> None:
        self._call("reportPresence", [world, entries, at], auth_world=world)

    def presence(self, max_age_ms: int) -> list[Presence]:
        raw = self._call("presence", [max_age_ms], list)
        if not isinstance(raw, list):
            return []
        return [_presence_row(row) for row in raw if isinstance(row, dict)]

    def record_rescued(self, world: str, name: str, saved_by: str, at: int = 0) -> None:
        self._call("recordRescued", [world, name, saved_by, at])

    def recent_rescued(self, limit: int) -> list[Rescued]:
        raw = self._call("recentRescued", [limit], list)
        if not isinstance(raw, list):
            return []
        return [_rescued_row(row) for row in raw if isinstance(row, dict)]

    def record_fallen(self, world: str, name: str, room: str, at: int = 0) -> None:
        self._call("recordFallen", [world, name, room, at])

    def recent_fallen(self, limit: int) -> list[Fallen]:
        raw = self._call("recentFallen", [limit], list)
        if not isinstance(raw, list):
            return []
        return [_fallen_row(row) for row in raw if isinstance(row, dict)]

    # Local-only helpers: remote worlds keep node memory on the world server.
    def record_local(self, node: str, kind: str, text: str) -> None:
        _ = (node, kind, text)

    def local_traces(self, node: str, limit: int) -> list:
        _ = (node, limit)
        return []

    def all_traces(self, limit: int) -> list[Trace]:
        _ = limit
        return []


def _trace_row(row: dict[str, Any]) -> Trace:
    return Trace(
        world=str(row.get("world", "")),
        node=str(row.get("node", "")),
        kind=str(row.get("kind", "")),
        text=str(row.get("text", "")),
        at=int(row.get("at", 0)),
    )


def _char_sheet_row(row: dict[str, Any]) -> CharSheet:
    return CharSheet(
        level=int(row.get("level", 1)),
        xp=int(row.get("xp", 0)),
        gold=int(row.get("gold", 0)),
        faction=str(row.get("faction", "")),
        morality=int(row.get("morality", 0)),
        title=str(row.get("title", "")),
        race=str(row.get("race", "")),
        ashsworn=bool(row.get("ashsworn", False)),
    )


def _sheet_row(sheet: CharSheet) -> dict[str, Any]:
    return {
        "level": sheet.level,
        "xp": sheet.xp,
        "gold": sheet.gold,
        "faction": sheet.faction,
        "morality": sheet.morality,
        "title": sheet.title,
        "race": sheet.race,
        "ashsworn": sheet.ashsworn,
    }


def _world_row(row: dict[str, Any]) -> WorldInfo:
    return WorldInfo(
        id=str(row.get("id", "")),
        url=str(row.get("url", "")),
        last_seen=int(row.get("last_seen", row.get("lastSeen", 0))),
    )


def _cast_row(row: dict[str, Any]) -> Cast:
    return Cast(
        id=int(row.get("id", 0)),
        world=str(row.get("world", "")),
        sender=str(row.get("sender", "")),
        text=str(row.get("text", "")),
    )


def _presence_row(row: dict[str, Any]) -> Presence:
    return Presence(
        world=str(row.get("world", "")),
        name=str(row.get("name", "")),
        regard=str(row.get("regard", "")),
        title=str(row.get("title", "")),
        at=int(row.get("at", 0)),
    )


def _rescued_row(row: dict[str, Any]) -> Rescued:
    return Rescued(
        world=str(row.get("world", "")),
        name=str(row.get("name", "")),
        saved_by=str(row.get("savedBy", row.get("saved_by", ""))),
        at=int(row.get("at", 0)),
    )


def _fallen_row(row: dict[str, Any]) -> Fallen:
    return Fallen(
        world=str(row.get("world", "")),
        name=str(row.get("name", "")),
        room=str(row.get("room", "")),
        at=int(row.get("at", 0)),
    )
