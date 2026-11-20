"""Canonical CharSheet persistence (protocol.md section 3 seam)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import fields
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


def sheet_to_json(sheet: CharSheet) -> str:
    return json.dumps(sheet.__dict__)


def sheet_from_json(raw: str) -> CharSheet:
    data = json.loads(raw)
    if not isinstance(data, dict):
        return CharSheet()
    known = {item.name for item in fields(CharSheet)}
    return CharSheet(**{key: data[key] for key in known if key in data})


class MemoryStore:
    """In-memory CharStore. The Worker flushes dirty rows to Durable Object storage."""

    def __init__(self) -> None:
        self._rows: dict[str, CharSheet | None] = {}
        self._dirty: set[str] = set()

    def seen(self, name: str) -> bool:
        return name_key(name) in self._rows

    def remember_json(self, name: str, raw: str | None) -> None:
        key = name_key(name)
        if not key:
            return
        if not raw:
            self._rows[key] = None
            return
        self._rows[key] = sheet_from_json(raw)

    def dirty_json(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for key in sorted(self._dirty):
            row = self._rows.get(key)
            if row is None:
                continue
            out.append((key, sheet_to_json(row)))
        self._dirty.clear()
        return out

    def load(self, name: str) -> tuple[CharSheet, bool]:
        key = name_key(name)
        if not key or key not in self._rows or self._rows[key] is None:
            return CharSheet(), False
        sheet = self._rows[key]
        assert sheet is not None
        return sheet, True

    def commit(self, name: str, sheet: CharSheet) -> None:
        key = name_key(name)
        if not key:
            raise ValueError("store: empty character name")
        self._rows[key] = sheet
        self._dirty.add(key)
