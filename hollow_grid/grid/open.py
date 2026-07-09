"""Open a Grid Hub client: remote HTTP RPC or in-process LocalHub."""

from __future__ import annotations

import os

from hollow_grid.grid.local_hub import LocalHub
from hollow_grid.grid.remote import RemoteHub

GridHub = LocalHub | RemoteHub


def open_grid_hub(
    world_name: str,
    world_url: str,
    *,
    hub_url: str | None = None,
    token: str | None = None,
) -> GridHub:
    url = hub_url if hub_url is not None else os.environ.get("GRID_HUB_URL", "")
    url = url.strip()
    if url:
        tok = token if token is not None else os.environ.get("GRID_HUB_TOKEN", "")
        return RemoteHub(url, tok.strip(), world_name, world_url)
    return LocalHub(world_name, world_url)
