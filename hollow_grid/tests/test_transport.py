"""Transport conformance: login, resume, movement (mirrors hollow-grid-go conn_test)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest

from websockets.asyncio.client import connect

from hollow_grid.transport.server import run_server


class TransportConformanceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._port = 18791
        self._task = asyncio.create_task(
            run_server(host="127.0.0.1", port=self._port, data_dir=self._tmpdir.name)
        )
        await asyncio.sleep(0.15)

    async def asyncTearDown(self) -> None:
        self._task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self._task
        self._tmpdir.cleanup()

    async def _dial(self):
        return await connect(f"ws://127.0.0.1:{self._port}/ws")

    def _must_contain(self, where: str, got: str, *wants: str) -> None:
        for want in wants:
            self.assertIn(want, got, f"{where}: missing {want!r} in {got!r}")

    async def test_login_race_move_and_scene(self) -> None:
        async with await self._dial() as ws:
            self._must_contain("name prompt", await ws.recv(), "wanderer")
            await ws.send("Tester")
            race_menu = await ws.recv()
            self._must_contain("race menu", race_menu, "choose what you are", "Human", "Revenant")
            await ws.send("human")
            entry = await ws.recv()
            self._must_contain(
                "entry scene",
                entry,
                "The Cracked Nexus",
                "Type 'help'",
                "@event room.info",
                '"id":"nexus"',
                '"north"',
                "@event char.vitals",
                '"maxHp":30',
                '"inCombat":false',
                "@event char.affects",
                '"addiction":0',
                '"faction":"none"',
                '"race":"human"',
                "@event room.actions",
                "@event world.state",
                '"phase":"day"',
                '"weather":"clear"',
            )
            await ws.send("down")
            tunnels = await ws.recv()
            self._must_contain("tunnels", tunnels, '"id":"tunnels"', "Service Tunnels")

    async def test_resume_persists_the_character(self) -> None:
        async with await self._dial() as ws:
            await ws.recv()
            await ws.send("Mara")
            await ws.recv()
            await ws.send("revenant")
            await ws.recv()

        async with await self._dial() as ws:
            await ws.recv()
            await ws.send("Mara")
            resumed = await ws.recv()
            self._must_contain("resume", resumed, "Welcome back", "Type 'help'", '"race":"revenant"')
            self.assertNotIn("choose what you are", resumed)


if __name__ == "__main__":
    unittest.main()
