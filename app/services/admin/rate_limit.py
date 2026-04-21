from __future__ import annotations

import hashlib
import time
from uuid import uuid4

from app.core.config import Settings

from .auth_common import _auth_state_unavailable
from .auth_state import require_redis_client

_FAILED_ATTEMPTS_KEY_PREFIX = "qa_admin:failed_auth_attempts:"


def _bucket_key(bucket: str) -> str:
    bucket_hash = hashlib.sha256(bucket.encode("utf-8")).hexdigest()
    return f"{_FAILED_ATTEMPTS_KEY_PREFIX}{bucket_hash}"


def _resolved_window_seconds(window_seconds: int) -> int:
    return max(1, int(window_seconds))


async def is_rate_limited(
    *,
    settings: Settings,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> bool:
    resolved_limit = max(1, int(limit))
    resolved_window = _resolved_window_seconds(window_seconds)
    now = time.time()
    client = await require_redis_client(settings)
    try:
        await client.zremrangebyscore(_bucket_key(bucket), "-inf", f"({now - resolved_window}")
        attempts = await client.zcard(_bucket_key(bucket))
    except Exception as exc:
        raise _auth_state_unavailable() from exc
    return int(attempts or 0) >= resolved_limit


async def record_failure(*, settings: Settings, bucket: str, window_seconds: int) -> None:
    resolved_window = _resolved_window_seconds(window_seconds)
    now = time.time()
    key = _bucket_key(bucket)
    client = await require_redis_client(settings)
    try:
        await client.zremrangebyscore(key, "-inf", f"({now - resolved_window}")
        await client.zadd(key, {f"{now}:{uuid4().hex}": now})
        await client.expire(key, resolved_window + 1)
    except Exception as exc:
        raise _auth_state_unavailable() from exc


async def clear_failures(*, settings: Settings, bucket: str) -> None:
    client = await require_redis_client(settings)
    try:
        await client.delete(_bucket_key(bucket))
    except Exception as exc:
        raise _auth_state_unavailable() from exc
