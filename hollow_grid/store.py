"""Canonical CharSheet persistence (protocol.md section 3 seam)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from hollow_grid.world.model import CharSheet

_KEY_UNSAFE = re.compile(r"[^a-z0-9_-]+")


def name_key(name: str) -> str:
    key = _KEY_UNSAFE.sub("-", name.strip().casefold())
    return key.strip("-")


class CharStore(Protocol):
    def load(self, name: str) -> tuple[CharSheet, bool]: ...

    def commit(self, name: str, sheet: CharSheet) -> None: ...


class FileStore:
    """One JSON file per character; swappable for a Grid hub client later."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path | None:
        key = name_key(name)
        if not key:
            return None
        return self._dir / f"{key}.json"

    def load(self, name: str) -> tuple[CharSheet, bool]:
        path = self._path(name)
        if path is None:
            return CharSheet(), False
        if not path.exists():
            return CharSheet(), False
        data = json.loads(path.read_text(encoding="utf-8"))
        return CharSheet(**data), True

    def commit(self, name: str, sheet: CharSheet) -> None:
        path = self._path(name)
        if path is None:
            raise ValueError("store: empty character name")
        payload = json.dumps(sheet.__dict__, indent=2)
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink()
