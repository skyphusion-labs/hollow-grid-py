"""Run a Verdigris Spool world server."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal

from hollow_grid.transport.server import DEFAULT_ADDR, DEFAULT_PORT, run_server
from hollow_grid.world import DEFAULT_WORLD_NAME, DEFAULT_WORLD_URL


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Hollow Grid world node (Verdigris Spool).")
    parser.add_argument("--host", default=_env("LISTEN_HOST", DEFAULT_ADDR))
    parser.add_argument("--port", type=int, default=int(_env("LISTEN_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--world-name", default=_env("WORLD_NAME", DEFAULT_WORLD_NAME))
    parser.add_argument("--world-url", default=_env("WORLD_URL", DEFAULT_WORLD_URL))
    parser.add_argument("--data", default=_env("DATA_DIR", "data"))
    parser.add_argument("--grid-hub-url", default=_env("GRID_HUB_URL", ""))
    parser.add_argument("--grid-hub-token", default=_env("GRID_HUB_TOKEN", ""))
    parser.add_argument("--admins", default=_env("ADMINS", "skyphusion"))
    args = parser.parse_args()

    grid_url = args.grid_hub_url.strip() or None
    grid_token = args.grid_hub_token.strip() or None

    async def _serve() -> None:
        task = asyncio.create_task(
            run_server(
                host=args.host,
                port=args.port,
                world_name=args.world_name,
                world_url=args.world_url,
                data_dir=args.data,
                admins=args.admins,
                grid_hub_url=grid_url,
                grid_hub_token=grid_token,
            )
        )
        loop = asyncio.get_running_loop()

        def _stop() -> None:
            task.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _stop)
        await task

    try:
        asyncio.run(_serve())
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    main()
