"""Worker session driver. No Cloudflare runtime required."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock

from hollow_grid.auth.passphrase import _pbkdf2_hash, verify_passphrase
from hollow_grid.grid.local_hub import LocalHub
from hollow_grid.store import MemoryStore
from hollow_grid.transport.cf_drive import (
    apply_snapshot,
    cf_begin,
    cf_feed,
    cf_init,
    drain_spawned,
    live_blob,
    restore_player,
    snapshot_world,
    task_mark,
)
from hollow_grid.transport.hub import LivePlayer, _push_best_effort, _wire_push
from hollow_grid.transport.server import WorldServer
from hollow_grid.transport.session import Session
from hollow_grid.world import build_world


class FakeConn:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_now(self, data: str) -> None:
        self.sent.append(data)

    async def send(self, data: str) -> None:
        self.send_now(data)

    def text(self) -> str:
        return "".join(self.sent)

    def clear(self) -> None:
        self.sent.clear()


class WorkerDriveTest(unittest.IsolatedAsyncioTestCase):
    async def test_login_look_and_quit(self) -> None:
        world = build_world("Verdigris Spool", "")
        store = MemoryStore()
        server = WorldServer(
            world=world,
            store=store,
            grid=LocalHub(world.name, world.url),
        )
        conn = FakeConn()
        session = Session(conn, server)
        await cf_begin(session)
        self.assertIn("wanderer", conn.text())
        conn.clear()

        self.assertFalse(await cf_feed(session, "Ada"))
        self.assertIn("@event char.create", conn.text())
        conn.clear()

        self.assertFalse(await cf_feed(session, "human"))
        self.assertIn("secret phrase", conn.text())
        conn.clear()

        self.assertFalse(await cf_feed(session, "grid-secret-phrase"))
        self.assertIn("The Cracked Nexus", conn.text())
        self.assertEqual(session._cf_phase, "play")
        self.assertTrue(store.dirty_json())
        conn.clear()

        self.assertFalse(await cf_feed(session, "look"))
        self.assertIn("The Cracked Nexus", conn.text())
        conn.clear()

        self.assertTrue(await cf_feed(session, "quit"))
        self.assertEqual(session._cf_phase, "closed")
        self.assertIn("goes quiet", conn.text())

    async def test_restore_keeps_the_room(self) -> None:
        world = build_world("Verdigris Spool", "")
        store = MemoryStore()
        server = WorldServer(
            world=world,
            store=store,
            grid=LocalHub(world.name, world.url),
        )
        conn = FakeConn()
        session = Session(conn, server)
        await cf_begin(session)
        self.assertFalse(await cf_feed(session, "Ada"))
        self.assertFalse(await cf_feed(session, "human"))
        self.assertFalse(await cf_feed(session, "grid-secret-phrase"))
        self.assertFalse(await cf_feed(session, "west"))
        assert session._player is not None
        room_id = session._player.room_id
        blob = live_blob(session)
        self.assertNotEqual(room_id, world.start().id)
        self.assertTrue(await cf_feed(session, "quit"))

        resumed = Session(FakeConn(), server)
        cf_init(resumed)
        resumed._cf_name = "Ada"
        resumed._cf_phase = "play"
        self.assertTrue(await restore_player(resumed, blob))
        assert resumed._player is not None
        self.assertEqual(resumed._player.room_id, room_id)

    async def test_drain_leaves_an_older_task(self) -> None:
        gate = asyncio.Event()

        async def linger() -> None:
            await gate.wait()

        old = asyncio.create_task(linger())
        before = task_mark()
        done = asyncio.Event()

        async def spawned() -> None:
            done.set()

        asyncio.create_task(spawned())
        await asyncio.wait_for(drain_spawned(before), timeout=1)
        self.assertTrue(done.is_set())
        self.assertFalse(old.done())
        gate.set()
        await old

    def test_snapshot_keeps_a_cache(self) -> None:
        world = build_world("Verdigris Spool", "")
        server = WorldServer(
            world=world,
            store=MemoryStore(),
            grid=LocalHub(world.name, world.url),
        )
        server.caches["workshop"] = 4
        saved = snapshot_world(server)
        server.caches.clear()
        apply_snapshot(server, saved)
        self.assertEqual(server.cache_gold("workshop"), 4)
        self.assertTrue(server.world.has_mob("rat"))

    def test_pbkdf2_roundtrip(self) -> None:
        stored = _pbkdf2_hash("grid-secret-phrase")
        self.assertTrue(verify_passphrase("grid-secret-phrase", stored))
        self.assertFalse(verify_passphrase("wrong-phrase-here", stored))

    def test_direct_send_matches_session_wire(self) -> None:
        sent: list[str] = []
        player = LivePlayer(
            name="Ada",
            room="nexus",
            title="",
            faction="none",
            race="human",
            ashsworn=False,
            morality=0,
            hp=30,
            max_hp=30,
            push=MagicMock(),
            send=sent.append,
        )
        _push_best_effort(player, "hello")
        self.assertEqual(sent, [_wire_push("hello")])
        player.push.put_nowait.assert_not_called()
