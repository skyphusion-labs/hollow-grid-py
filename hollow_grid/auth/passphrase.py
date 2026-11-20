"""Character login passphrase hashing (K3 audit #38)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_MIN_LEN = 8
_MAX_LEN = 128
_PBKDF_ITERS = 200_000
_PBKDF_PREFIX = "pbkdf2_sha256$"


def hash_passphrase(phrase: str) -> str:
    phrase = phrase.strip()
    if len(phrase) < _MIN_LEN:
        raise ValueError("passphrase too short")
    if len(phrase) > _MAX_LEN:
        raise ValueError("passphrase too long")
    try:
        import bcrypt
    except ImportError:
        return _pbkdf2_hash(phrase)
    digest = bcrypt.hashpw(phrase.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("ascii")


def verify_passphrase(phrase: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    phrase = phrase.strip()
    if len(phrase) > _MAX_LEN:
        return False
    if stored_hash.startswith(_PBKDF_PREFIX):
        return _pbkdf2_verify(phrase, stored_hash)
    try:
        import bcrypt
    except ImportError:
        return False
    try:
        return bcrypt.checkpw(phrase.encode("utf-8"), stored_hash.encode("ascii"))
    except ValueError:
        return False


def _pbkdf2_hash(phrase: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", phrase.encode("utf-8"), salt.encode("ascii"), _PBKDF_ITERS)
    return f"{_PBKDF_PREFIX}{_PBKDF_ITERS}${salt}${dk.hex()}"


def _pbkdf2_verify(phrase: str, stored_hash: str) -> bool:
    try:
        _prefix, iters_s, salt, hexdigest = stored_hash.split("$", 3)
    except ValueError:
        return False
    try:
        iters = int(iters_s)
    except ValueError:
        return False
    if iters < 100_000 or iters > 1_000_000:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", phrase.encode("utf-8"), salt.encode("ascii"), iters)
    return hmac.compare_digest(dk.hex(), hexdigest)
