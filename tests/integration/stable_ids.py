from __future__ import annotations

import hashlib


def _stable_number(*parts: object, modulo: int) -> int:
    payload = "::".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") % modulo


def stable_telegram_user_id(*, prefix: int, seed: str) -> int:
    return prefix + _stable_number("telegram_user", prefix, seed, modulo=1_000_000_000_000)


def stable_int_id(*parts: object, modulo: int = 1_000_000_000) -> int:
    return _stable_number("int_id", *parts, modulo=modulo) + 1
