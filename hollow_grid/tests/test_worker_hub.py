"""Test the Python Worker's GridHubService contract without a JS runtime."""

from __future__ import annotations

import unittest
from typing import Any

from hollow_grid.grid.local_hub import CharSheet
from hollow_grid.grid.remote import GridHubError
from hollow_grid.grid.worker_hub import WorkerHub


class StubWorkerHub(WorkerHub):
    def __init__(self) -> None:
        super().__init__(None, "Verdigris Spool", "wss://verdigris.example/ws", "world-key")
        self.calls: list[tuple[str, list[Any]]] = []

    async def _invoke(self, method: str, args: list[Any]) -> Any:
        self.calls.append((method, args))
        if method == "loadCharacter":
            return {"race": "", "faction": "none", "gold": 20}
        if method == "shiftTide":
            return -5
        if method == "presence":
            return []
        if method == "pruneLedgerKinds":
            raise RuntimeError("denied")
        return None


class WorkerHubTest(unittest.IsolatedAsyncioTestCase):
    async def test_bindings_supply_the_world_identity(self) -> None:
        hub = StubWorkerHub()
        await hub.register(hub.world_name, hub.world_url)
        await hub.ping()
        self.assertEqual(await hub.shift_tide(-10), -5)
        await hub.commit_character("Mara", CharSheet(race="human"))

        self.assertEqual(hub.calls[0], ("register", [hub.world_name, hub.world_url, hub.world_key]))
        self.assertEqual(hub.calls[1], ("presence", [1, hub.world_name, hub.world_key]))
        self.assertEqual(hub.calls[2], ("shiftTide", [-10, hub.world_name, hub.world_key]))
        method, args = hub.calls[3]
        self.assertEqual(method, "commitCharacter")
        self.assertEqual(args[:2], ["Mara", hub.world_name])
        self.assertEqual(args[2]["race"], "human")
        self.assertEqual(args[3], hub.world_key)

    async def test_missing_character_and_rpc_failure(self) -> None:
        hub = StubWorkerHub()
        _, found = await hub.load_character("Mara")
        self.assertFalse(found)
        self.assertEqual(hub.calls[0], ("loadCharacter", ["Mara", hub.world_name, hub.world_key]))
        with self.assertRaisesRegex(GridHubError, "pruneLedgerKinds"):
            await hub.prune_ledger_kinds(["trace"])
