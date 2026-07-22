import unittest

from hollow_grid.transport.sanitize import sanitize_player_name, sanitize_player_text


class SanitizeTests(unittest.TestCase):
    def test_name_rejects_crlf(self) -> None:
        self.assertIsNone(sanitize_player_name("bad\r\n@event"))

    def test_name_accepts_simple(self) -> None:
        self.assertEqual(sanitize_player_name("alice"), "alice")

    def test_text_strips_newlines(self) -> None:
        self.assertEqual(
            sanitize_player_text("hello\r\n@event char.vitals {}"),
            "hello @event char.vitals {}",
        )


if __name__ == "__main__":
    unittest.main()
