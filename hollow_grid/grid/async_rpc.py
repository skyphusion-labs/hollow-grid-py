"""Run blocking Grid Hub RPC off the asyncio event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from hollow_grid.grid.open import GridHub

T = TypeVar("T")


async def grid_rpc(grid: GridHub | None, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    if grid is None or not grid.remote():
        return fn(*args, **kwargs)
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except NotImplementedError as exc:
        raise RuntimeError(
            "The Worker has no thread pool. Federation stays on the process server."
        ) from exc
