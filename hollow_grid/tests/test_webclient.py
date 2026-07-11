"""Tests for the browser play page HTML and HTTP route."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import unittest

from websockets.asyncio.client import connect

from hollow_grid.transport.server import run_server
from hollow_grid.transport.webclient import play_page


class PlayPageTest(unittest.TestCase):
    def test_contains_xterm_and_world_name(self) -> None:
        body = play_page("Verdigris Spool")
        for want in ("Verdigris Spool", "xterm", "@event ", "/ws", "the hollow grid network"):
            self.assertIn(want, body)

    def test_escapes_title(self) -> None:
        body = play_page('<script>alert("x")</script>')
        self.assertNotIn("<script>alert", body)


class PlayPageRouteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._port = 18792
        self._task = asyncio.create_task(
            run_server(host="127.0.0.1", port=self._port, data_dir=self._tmpdir.name)
        )
        await asyncio.sleep(0.5)

    async def asyncTearDown(self) -> None:
        self._task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self._task
        self._tmpdir.cleanup()

    async def test_get_root_serves_play_page(self) -> None:
        url = f"http://127.0.0.1:{self._port}/"
        proc = await asyncio.create_subprocess_exec(
            "curl",
            "-sf",
            "-m",
            "5",
            url,
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        self.assertEqual(proc.returncode, 0, stdout)
        body = stdout.decode("utf-8")
        self.assertIn("xterm", body)
        self.assertIn("Verdigris Spool", body)

    async def test_ws_still_upgrades(self) -> None:
        async with await connect(f"ws://127.0.0.1:{self._port}/ws") as ws:
            banner = await asyncio.wait_for(ws.recv(), timeout=5)
            self.assertIn("wanderer", banner)


if __name__ == "__main__":
    unittest.main()
