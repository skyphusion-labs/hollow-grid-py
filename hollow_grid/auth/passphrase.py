"""Character login passphrase hashing (K3 audit #38)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from typing import TypeVar

_MIN_LEN = 8
_MAX_LEN = 128
_PBKDF_ITERS = 200_000
_PBKDF_PREFIX = "pbkdf2_sha256$"
T = TypeVar("T")


def hasher_name() -> str:
    """Which hasher this process can use. bcrypt when the wheel imports."""
    try:
        import bcrypt
    except ImportError:
        return "pbkdf2_sha256"
    del bcrypt
    return "bcrypt"


async def hash_passphrase_async(phrase: str) -> str:
    """Hash a passphrase without holding the Worker isolate on bcrypt."""
    phrase = phrase.strip()
    if len(phrase) < _MIN_LEN:
        raise ValueError("passphrase too short")
    if len(phrase) > _MAX_LEN:
        raise ValueError("passphrase too long")
    web = await _webcrypto_pbkdf2_hash(phrase)
    if web is not None:
        return web
    return await _off_thread(hash_passphrase, phrase)


async def verify_passphrase_async(phrase: str, stored_hash: str) -> bool:
    """Check a passphrase. WebCrypto handles pbkdf2 on the Worker."""
    if not stored_hash:
        return False
    phrase = phrase.strip()
    if len(phrase) > _MAX_LEN:
        return False
    if stored_hash.startswith(_PBKDF_PREFIX):
        web = await _webcrypto_pbkdf2_verify(phrase, stored_hash)
        if web is not None:
            return web
    return await _off_thread(verify_passphrase, phrase, stored_hash)


async def _off_thread(fn: Callable[..., T], *args: object) -> T:
    import asyncio

    try:
        return await asyncio.to_thread(fn, *args)
    except NotImplementedError:
        return fn(*args)


async def _webcrypto_pbkdf2_hash(phrase: str) -> str | None:
    salt = secrets.token_bytes(16)
    digest = await _webcrypto_derive(phrase, salt, _PBKDF_ITERS)
    if digest is None:
        return None
    return f"{_PBKDF_PREFIX}{_PBKDF_ITERS}${salt.hex()}${digest.hex()}"


async def _webcrypto_pbkdf2_verify(phrase: str, stored_hash: str) -> bool | None:
    try:
        _prefix, iters_s, salt_hex, hexdigest = stored_hash.split("$", 3)
    except ValueError:
        return False
    try:
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    if iters < 100_000 or iters > 1_000_000:
        return False
    digest = await _webcrypto_derive(phrase, salt, iters)
    if digest is None:
        return None
    return hmac.compare_digest(digest.hex(), hexdigest)


async def _webcrypto_derive(phrase: str, salt: bytes, iters: int) -> bytes | None:
    try:
        from js import Object, Uint8Array, crypto  # type: ignore[import-not-found]
        from pyodide.ffi import to_js  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        raw = Uint8Array.new(to_js(list(phrase.encode("utf-8"))))
        key = await crypto.subtle.importKey("raw", raw, "PBKDF2", False, to_js(["deriveBits"]))
        params = to_js(
            {
                "name": "PBKDF2",
                "salt": Uint8Array.new(to_js(list(salt))),
                "iterations": iters,
                "hash": "SHA-256",
            },
            dict_converter=Object.fromEntries,
        )
        bits = await crypto.subtle.deriveBits(params, key, 256)
        view = Uint8Array.new(bits)
        return bytes(view.to_py())
    except Exception:
        return None


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
