"""Grid Hub RPC over the Cloudflare Worker service binding."""

from __future__ import annotations

import asyncio
from typing import Any

from hollow_grid.grid.remote import GridHubError, RemoteHub

_RPC_TIMEOUT_SEC = 2


class WorkerHub(RemoteHub):
    def __init__(self, binding: Any, world_name: str, world_url: str, world_key: str) -> None:
        super().__init__("", world_name=world_name, world_url=world_url, world_key=world_key)
        self.binding = binding

    async def _call(self, method: str, params: list[Any], *, auth_world: str = "") -> Any:
        args = params.copy()
        if method in {"shiftTide", "pruneLedgerKinds", "presence"}:
            args.append(self.world_name)
            auth_world = self.world_name
        if auth_world:
            args.append(self.world_key)
        try:
            result = await asyncio.wait_for(self._invoke(method, args), _RPC_TIMEOUT_SEC)
        except Exception as exc:
            raise GridHubError(f"grid binding {method}: {exc}") from exc
        return result

    async def _invoke(self, method: str, args: list[Any]) -> Any:
        from js import Object  # type: ignore[import-not-found]
        from pyodide.ffi import JsProxy, to_js  # type: ignore[import-not-found]

        rpc = getattr(self.binding, method)
        encoded = [to_js(arg, dict_converter=Object.fromEntries) for arg in args]
        result = await rpc(*encoded)
        return result.to_py() if isinstance(result, JsProxy) else result

    async def ping(self) -> None:
        # Presence validates the world key. The public tide read would not.
        await self.presence(1)
