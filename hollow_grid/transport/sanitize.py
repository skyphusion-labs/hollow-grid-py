"""Sanitize player-authored strings before cross-client broadcast."""

from __future__ import annotations

import re

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


def sanitize_player_name(name: str) -> str | None:
    name = name.strip()
    if not _NAME_RE.fullmatch(name):
        return None
    return name


def sanitize_player_text(text: str, *, limit: int = 500) -> str:
    chars: list[str] = []
    for ch in text:
        if ch in "\r\n":
            chars.append(" ")
        elif ch == "\t" or (" " <= ch <= "~"):
            chars.append(ch)
    out = " ".join("".join(chars).split())
    if len(out) > limit:
        out = out[:limit].rstrip()
    return out
