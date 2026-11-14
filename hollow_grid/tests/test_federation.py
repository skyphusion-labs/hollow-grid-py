"""Federation loop resilience (gridcast relay must not die silently)."""

from __future__ import annotations

import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from hollow_grid.transport import federation
from hollow_grid.transport.hub import LivePlayer, _push_best_effort


class FederationResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_poll_gridcasts_exception_does_not_exit_loop(self) -> None:
        server = MagicMock()
        server.world.name = "Test"
        server.log = logging.getLogger("test_federation")
        server.grid = MagicMock()
        server.grid.remote.return_value = True
        server._lock = asyncio.Lock()
        server.last_tide = 0
        server.hub = MagicMock()
        server.hub.all_players = AsyncMock(return_value=[])
        server.poll_gridcasts = AsyncMock(side_effect=[RuntimeError("boom"), None])

        with patch.object(federation, "advance_cast_cursor", new_callable=AsyncMock, return_value=0), patch(
            "hollow_grid.transport.federation.grid_rpc", new_callable=AsyncMock, return_value=0
        ), patch.object(federation, "report_presence", new_callable=AsyncMock):
            task = asyncio.create_task(
                federation.run_federation(server, default_port=19999),
            )
            await asyncio.sleep(4.5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertGreaterEqual(server.poll_gridcasts.await_count, 2)

    async def test_register_retries_until_success(self) -> None:
        server = MagicMock()
        server.world.name = "Test"
        server.log = logging.getLogger("test_federation_register")
        grid = MagicMock()
        register_attempts = 0

        async def grid_rpc_side_effect(grid_arg, method, *args, **kwargs):
            nonlocal register_attempts
            register_attempts += 1
            if register_attempts < 3:
                raise TimeoutError("read timed out")
            return None

        mock_rpc = AsyncMock(side_effect=grid_rpc_side_effect)

        async def instant_sleep(_: float) -> None:
            return

        with patch("hollow_grid.transport.federation.grid_rpc", mock_rpc), patch.object(
            asyncio, "sleep", side_effect=instant_sleep
        ):
            await federation._register_until_ok(server, grid, "ws://127.0.0.1:19999/ws")

        self.assertEqual(register_attempts, 3)

    async def test_empty_world_url_skips_hub_registration(self) -> None:
        """No WORLD_URL means skip hub register; log once; do not raise."""
        from hollow_grid.world import DEFAULT_WORLD_URL, build_world

        world = build_world()
        self.assertEqual(DEFAULT_WORLD_URL, "")
        self.assertEqual(world.url, "")
        self.assertNotIn("verdigris", world.url.casefold())

        server = MagicMock()
        server.world = world
        server.log = logging.getLogger("test_empty_world_url")
        server.grid = MagicMock()
        server.grid.remote.return_value = True
        server._lock = asyncio.Lock()
        server.last_tide = 0
        server.hub = MagicMock()
        server.hub.all_players = AsyncMock(return_value=[])
        server.poll_gridcasts = AsyncMock()

        mock_rpc = AsyncMock(return_value=0)

        with patch.object(
            federation, "advance_cast_cursor", new_callable=AsyncMock, return_value=0
        ), patch(
            "hollow_grid.transport.federation.grid_rpc", mock_rpc
        ), patch.object(federation, "report_presence", new_callable=AsyncMock):
            with self.assertLogs("test_empty_world_url", level="INFO") as logs:
                task = asyncio.create_task(
                    federation.run_federation(server, default_port=8791),
                )
                await asyncio.sleep(0.2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

        registered_urls: list[str] = []
        for call in mock_rpc.await_args_list:
            if len(call.args) >= 2 and call.args[1] is server.grid.register:
                registered_urls.append(call.args[3] if len(call.args) > 3 else "")
        for url in registered_urls:
            self.assertNotIn("verdigris", url.casefold())
        self.assertEqual(registered_urls, [])
        self.assertTrue(any("WORLD_URL unset" in line for line in logs.output))

    def test_push_best_effort_survives_broken_queue(self) -> None:
        lp = LivePlayer(
            name="broken",
            room="nexus",
            title="",
            faction="none",
            race="human",
            ashsworn=False,
            morality=0,
            hp=30,
            max_hp=30,
            push=MagicMock(),
        )
        lp.push.put_nowait.side_effect = RuntimeError("queue dead")
        with self.assertLogs("hollow_grid", level="WARNING") as logs:
            _push_best_effort(lp, "hello", player="broken")
        self.assertTrue(any("broadcast push failed" in line for line in logs.output))


class FedTaskDoneCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_done_callback_logs_exception(self) -> None:
        log = logging.getLogger("hollow_grid_test")

        async def boom() -> None:
            raise ValueError("fed died")

        task = asyncio.create_task(boom())

        def on_done(t: asyncio.Task[None]) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                log.error("federation task died world=%s", "Test", exc_info=exc)

        task.add_done_callback(on_done)
        with self.assertLogs("hollow_grid_test", level="ERROR") as logs:
            with self.assertRaises(ValueError):
                await task
        self.assertTrue(any("federation task died" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
