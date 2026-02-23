from __future__ import annotations

import secrets
from datetime import datetime, timezone

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_raw_codes(
    *,
    count: int,
    token_length: int = 8,
    prefix: str = "",
    existing_codes: set[str] | None = None,
) -> list[str]:
    if count <= 0:
        raise ValueError("count must be positive")
    if token_length <= 0:
        raise ValueError("token_length must be positive")

    existing = existing_codes if existing_codes is not None else set()
    generated: list[str] = []
    attempts = 0
    max_attempts = max(100, count * 50)

    while len(generated) < count:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError("unable to generate unique promo codes")

        token = "".join(secrets.choice(CODE_ALPHABET) for _ in range(token_length))
        raw_code = f"{prefix}{token}" if prefix else token
        if raw_code in existing:
            continue

        existing.add(raw_code)
        generated.append(raw_code)

    return generated


def parse_utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
