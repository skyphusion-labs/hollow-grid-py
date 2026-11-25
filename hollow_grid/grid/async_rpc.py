"""Call either the local grid or an asynchronous federation client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any, TypeVar

from hollow_grid.grid.open import GridHub

T = TypeVar("T")


async def grid_rpc(
    _grid: GridHub | None, fn: Callable[..., T | Awaitable[T]], /,
    *args: Any, **kwargs: Any,
) -> T:
    result = fn(*args, **kwargs)
    if isawaitable(result):
        return await result
    return result
