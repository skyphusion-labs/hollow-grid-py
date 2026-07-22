"""Remote Grid Hub JSON-RPC client tests (mock HTTP)."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hollow_grid.grid.local_hub import CharSheet
from hollow_grid.grid.remote import GridHubError, RemoteHub


class _RpcHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        _ = (format, args)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        method = body.get("method")
        params = body.get("params", [])
        auth = self.headers.get("Authorization", "")

        if auth != "Bearer test-token":
            self._json(401, {"ok": False, "error": "unauthorized"})
            return

        if method == "tide":
            self._json(200, {"ok": True, "result": -12})
            return
        if method == "shiftTide":
            self._json(200, {"ok": True, "result": int(params[0]) + 3})
            return
        if method == "listWorlds":
            self._json(200, {
                "ok": True,
                "result": [
                    {"id": "Dustfall", "url": "wss://dustfall.skyphusion.org/ws", "last_seen": 1},
                ],
            })
            return
        if method == "loadCharacter":
            self._json(200, {
                "ok": True,
                "result": {
                    "level": 3,
                    "xp": 10,
                    "gold": 40,
                    "faction": "ally",
                    "morality": 5,
                    "title": "runner",
                    "race": "human",
                    "ashsworn": False,
                },
            })
            return
        if method == "recentAcross":
            self._json(200, {
                "ok": True,
                "result": [
                    {"world": "Dustfall", "node": "market", "kind": "slain", "text": "echo", "at": 1},
                ],
            })
            return
        self._json(400, {"ok": False, "error": f"unknown method: {method}"})

    def _json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class RemoteHubTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _RpcHandler)
        cls._thread = threading.Thread(target=cls._httpd.serve_forever, daemon=True)
        cls._thread.start()
        host, port = cls._httpd.server_address
        cls._url = f"http://{host}:{port}/rpc"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpd.shutdown()
        cls._thread.join(timeout=2)

    def test_tide_and_shift(self) -> None:
        hub = RemoteHub(self._url, "test-token", "Verdigris Spool")
        self.assertEqual(hub.tide(), -12)
        self.assertEqual(hub.shift_tide(5), 8)

    def test_list_worlds_and_load_character(self) -> None:
        hub = RemoteHub(self._url, "test-token", "Verdigris Spool")
        worlds = hub.list_worlds()
        self.assertEqual(worlds[0].id, "Dustfall")
        sheet, found = hub.load_character("Mara")
        self.assertTrue(found)
        self.assertEqual(sheet.level, 3)
        self.assertEqual(sheet.faction, "ally")

    def test_commit_and_lease_send_world(self) -> None:
        seen: dict[str, object] = {}

        class _CaptureHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                _ = (format, args)

            def do_POST(self) -> None:
                if self.headers.get("Authorization", "") != "Bearer test-token":
                    self.send_response(401)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                seen["method"] = body.get("method")
                seen["params"] = body.get("params")
                seen["world"] = self.headers.get("X-Grid-World")
                data = json.dumps({"ok": True, "result": None}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        url = f"http://{host}:{port}/rpc"
        try:
            hub = RemoteHub(url, "test-token", "Verdigris Spool", world_key="sekrit")
            hub.commit_character("Mara", CharSheet(level=3, faction="ally"))
            self.assertEqual(seen["method"], "commitCharacter")
            self.assertEqual(seen["params"][1], "Verdigris Spool")
            self.assertEqual(seen["world"], "Verdigris Spool")
            hub.claim_character_lease("Mara")
            self.assertEqual(seen["method"], "claimCharacterLease")
        finally:
            httpd.shutdown()
            thread.join(timeout=2)

    def test_recent_across(self) -> None:
        hub = RemoteHub(self._url, "test-token", "Verdigris Spool")
        traces = hub.recent_across("Verdigris Spool", 5)
        self.assertEqual(traces[0].world, "Dustfall")

    def test_unauthorized_raises(self) -> None:
        hub = RemoteHub(self._url, "wrong")
        with self.assertRaises(GridHubError):
            hub.tide()


if __name__ == "__main__":
    unittest.main()
