"""Transport conformance: login, resume, movement (mirrors hollow-grid-go conn_test)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest

from websockets.asyncio.client import connect

from hollow_grid.transport.server import run_server


TEST_PASSPHRASE = "grid-secret-phrase"
# Test-only keeper token; never used in production fleet rolls.
TEST_ADMIN_TOKEN = "test-keeper-token-for-ci-only"

class TransportConformanceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._port = 18791
        self._task = asyncio.create_task(
            run_server(
                host="127.0.0.1",
                port=self._port,
                data_dir=self._tmpdir.name,
                admin_token=TEST_ADMIN_TOKEN,
            )
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

    async def _login(self, ws, name: str, race: str = "human") -> str:
        self._must_contain("name prompt", await ws.recv(), "wanderer")
        await ws.send(name)
        if name.casefold() == "skyphusion":
            self._must_contain("keeper token", await ws.recv(), "keeper's token")
            await ws.send(TEST_ADMIN_TOKEN)
        race_menu = await ws.recv()
        if "secret phrase" in race_menu and "choose what you are" not in race_menu:
            await ws.send(TEST_PASSPHRASE)
            welcome = await ws.recv()
            self._must_contain("resume", welcome, "Welcome back")
            return welcome
        self._must_contain("race menu", race_menu, "choose what you are", "@event char.create")
        create = self._last_event(race_menu, "char.create")
        assert create is not None
        self.assertEqual(create.get("prompt"), "race")
        self.assertTrue(isinstance(create.get("races"), list) and len(create["races"]) > 0)
        await ws.send(race)
        self._must_contain("passphrase new", await ws.recv(), "secret phrase")
        await ws.send(TEST_PASSPHRASE)
        entry = await ws.recv()
        self._must_contain("entry scene", entry, "The Cracked Nexus", "@event room.info")
        return entry

    async def test_char_create_reemits_on_invalid_race(self) -> None:
        async with await self._dial() as ws:
            self._must_contain("name prompt", await ws.recv(), "wanderer")
            await ws.send("BadRacer")
            race_menu = await ws.recv()
            self._must_contain("race menu", race_menu, "choose what you are", "@event char.create")
            await ws.send("not-a-race")
            retry = await ws.recv()
            self._must_contain("invalid race", retry, "does not recognize", "@event char.create")
            create = self._last_event(retry, "char.create")
            assert create is not None
            self.assertEqual(create.get("prompt"), "race")

    def _last_event(self, text: str, name: str) -> dict | None:
        import json

        last: dict | None = None
        for line in text.splitlines():
            if not line.startswith("@event "):
                continue
            rest = line[7:]
            sp = rest.find(" ")
            if sp < 0:
                continue
            ev_name, body = rest[:sp], rest[sp + 1 :]
            if ev_name == name:
                last = json.loads(body)
        return last

    async def test_worlds_lists_local_world_and_saltreach(self) -> None:
        async with await self._dial() as ws:
            await self._login(ws, "Worlder")
            await ws.send("worlds")
            out = await ws.recv()
            self._must_contain("worlds", out, "Worlds linked on the Grid", "Saltreach", "@event grid.worlds")
            payload = self._last_event(out, "grid.worlds")
            assert payload is not None
            worlds = payload["worlds"]
            self.assertTrue(any(w.get("here") and w.get("id") == "Verdigris Spool" for w in worlds))
            self.assertTrue(any("Saltreach" in w.get("id", "") for w in worlds))

    async def test_travel_saltreach_emits_grid_travel(self) -> None:
        async with await self._dial() as ws:
            await self._login(ws, "Traveler")
            await ws.send("travel Saltreach")
            out = await ws.recv()
            self._must_contain(
                "travel",
                out,
                "routes you toward Saltreach",
                "saltreach.example",
                "@event grid.travel",
            )
            payload = self._last_event(out, "grid.travel")
            assert payload is not None
            self.assertEqual(payload["to"], "Saltreach")
            self.assertIn("saltreach.example", payload["url"])

    async def _recv_until(self, ws, pred, timeout: float = 3.0) -> str:
        deadline = asyncio.get_event_loop().time() + timeout
        buf = ""
        while asyncio.get_event_loop().time() < deadline:
            try:
                chunk = await asyncio.wait_for(ws.recv(), timeout=0.2)
            except TimeoutError:
                continue
            buf += chunk
            if pred(buf):
                return buf
        return buf

    async def _drain(self, ws, timeout: float = 0.3) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.05)
            except TimeoutError:
                break

    async def test_tell_and_reply_deliver_comm_tell(self) -> None:
        async with await self._dial() as a, await self._dial() as b:
            await self._login(a, "Alf")
            await self._login(b, "Bex")
            await self._drain(a)
            await a.send("tell Bex you there?")
            self._must_contain("tell ack", await a.recv(), "You tell Bex")
            told = await b.recv()
            self._must_contain("tell delivery", told, "Alf tells you", "@event comm.tell")
            payload = self._last_event(told, "comm.tell")
            assert payload is not None
            self.assertEqual(payload["from"], "Alf")
            self.assertIn("you there", payload["text"])
            await b.send("reply loud and clear")
            reply = await self._recv_until(
                a,
                lambda text: "Bex tells you" in text and "loud and clear" in text and "@event comm.tell" in text,
            )
            self._must_contain("reply delivery", reply, "Bex tells you", "loud and clear", "@event comm.tell")

    async def test_login_race_move_and_scene(self) -> None:
        async with await self._dial() as ws:
            entry = await self._login(ws, "Tester", "human")
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
            await self._login(ws, "Mara", "revenant")

        async with await self._dial() as ws:
            self._must_contain("name prompt", await ws.recv(), "wanderer")
            await ws.send("Mara")
            self._must_contain("passphrase resume", await ws.recv(), "secret phrase")
            await ws.send(TEST_PASSPHRASE)
            resumed = await ws.recv()
            self._must_contain("resume", resumed, "Welcome back", "Type 'help'", '"race":"revenant"')
            self.assertNotIn("choose what you are", resumed)

    async def test_treat_at_nexus_refuses_medic(self) -> None:
        async with await self._dial() as ws:
            await self._login(ws, "Medchk")
            await ws.send("treat")
            out = await ws.recv()
            self._must_contain("medic gate", out, "no medic here", "waystation")

    async def test_treat_during_login_refuses_medic_at_nexus(self) -> None:
        """Smoke sends treat before room.info; login drain must answer early."""
        async with await self._dial() as ws:
            self._must_contain("name prompt", await ws.recv(), "wanderer")
            await ws.send("Medearly")
            await ws.recv()
            await ws.send("human")
            await ws.send("treat")
            out = await self._recv_until(ws, lambda t: "no medic here" in t, 5)
            self._must_contain("medic gate during login", out, "no medic here", "waystation")

    async def test_resume_whoami_during_login_emits_identity(self) -> None:
        async with await self._dial() as ws:
            await self._login(ws, "Relog")
            await ws.send("north")
            await ws.recv()
            await ws.send("defend")
            await self._recv_until(ws, lambda t: "@event char.affects" in t, 3)

        async with await self._dial() as ws:
            await ws.recv()
            await ws.send("Relog")
            await ws.send("whoami")
            out = await self._recv_until(ws, lambda t: "@event char.identity" in t, 5)
            payload = self._last_event(out, "char.identity")
            assert payload is not None
            self.assertEqual(payload["faction"], "ally")

    async def test_witness_during_login_emits_grid_fallen(self) -> None:
        async with await self._dial() as ws:
            self._must_contain("name prompt", await ws.recv(), "wanderer")
            await ws.send("Vigil")
            await ws.recv()
            await ws.send("human")
            await ws.send("witness")
            out = await self._recv_until(ws, lambda t: "@event grid.fallen" in t, 5)
            payload = self._last_event(out, "grid.fallen")
            assert payload is not None
            self.assertIsInstance(payload["fallen"], list)

    async def test_holding_pit_free_emits_grid_rescued_before_persist(self) -> None:
        async with await self._dial() as ws:
            await self._login(ws, "Pitfree")
            for cmd in ("north", "north", "attack warden"):
                await ws.send(cmd)
                await asyncio.sleep(0.05)
            await self._recv_until(ws, lambda t: "combat.end" in t and '"result":"killed"' in t, 30)
            await ws.send("free")
            out = await self._recv_until(ws, lambda t: "@event grid.rescued" in t, 5)
            rescued = self._last_event(out, "grid.rescued")
            assert rescued is not None
            self.assertEqual(rescued["savedBy"], "Pitfree")
            self.assertEqual(len(rescued["freed"]), 1)
            affects = self._last_event(out, "char.affects")
            assert affects is not None
            self.assertGreater(affects["morality"], 0)


if __name__ == "__main__":
    unittest.main()
