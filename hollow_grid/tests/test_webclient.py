"""Tests for the browser play page HTML."""

from __future__ import annotations

import unittest

from hollow_grid.transport.webclient import play_page


class PlayPageTest(unittest.TestCase):
    def test_contains_xterm_and_world_name(self) -> None:
        body = play_page("Verdigris Spool")
        for want in ("Verdigris Spool", "xterm", "@event ", "/ws", "the hollow grid network"):
            self.assertIn(want, body)

    def test_escapes_title(self) -> None:
        body = play_page('<script>alert("x")</script>')
        self.assertNotIn("<script>alert", body)


if __name__ == "__main__":
    unittest.main()
