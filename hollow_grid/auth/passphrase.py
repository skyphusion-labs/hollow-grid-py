"""Character login passphrase hashing (K3 audit #38)."""

from __future__ import annotations

import bcrypt

_MIN_LEN = 8
_MAX_LEN = 128


def hash_passphrase(phrase: str) -> str:
    phrase = phrase.strip()
    if len(phrase) < _MIN_LEN:
        raise ValueError("passphrase too short")
    if len(phrase) > _MAX_LEN:
        raise ValueError("passphrase too long")
    digest = bcrypt.hashpw(phrase.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("ascii")


def verify_passphrase(phrase: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    phrase = phrase.strip()
    if len(phrase) > _MAX_LEN:
        return False
    try:
        return bcrypt.checkpw(phrase.encode("utf-8"), stored_hash.encode("ascii"))
    except ValueError:
        return False
