"""Federation gridcast cursor and poll behavior."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from hollow_grid.grid.local_hub import Cast
from hollow_grid.grid.remote import GridHubError
from hollow_grid.transport.federation import advance_cast_cursor


@dataclass
class FakeCastGrid:
    casts: list[Cast] = field(default_factory=list)

    def remote(self) -> bool:
        return True

    def casts_since(self, since_id: int, limit: int) -> list[Cast]:
        rows = [c for c in self.casts if c.id > since_id]
        if limit > 0:
            rows = rows[:limit]
        return rows


class AdvanceCastCursorTest(unittest.IsolatedAsyncioTestCase):
    async def test_skips_backlog_to_hub_head(self) -> None:
        grid = FakeCastGrid(casts=[Cast(i, "W", "p", "t") for i in range(1, 121)])
        head = await advance_cast_cursor(grid)
        self.assertEqual(head, 120)

    async def test_empty_hub_returns_zero(self) -> None:
        head = await advance_cast_cursor(FakeCastGrid())
        self.assertEqual(head, 0)


if __name__ == "__main__":
    unittest.main()
