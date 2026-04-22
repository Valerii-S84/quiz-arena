from __future__ import annotations

from collections.abc import Iterable

from app.core.config import Settings

from .auth_common import _auth_state_unavailable
from .auth_state import _require_redis_client

_ADMIN_RATE_LIMIT_KEY_PREFIX = "qa_admin:rate_limit:"


def _rate_limit_key(bucket: str) -> str:
    return f"{_ADMIN_RATE_LIMIT_KEY_PREFIX}{bucket}"


def _normalize_buckets(buckets: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_bucket in buckets:
        bucket = raw_bucket.strip()
        if not bucket or bucket in seen:
            continue
        seen.add(bucket)
        normalized.append(bucket)
    return tuple(normalized)


async def is_rate_limited(
    *,
    settings: Settings,
    buckets: Iterable[str],
    limit: int,
    window_seconds: int,
) -> bool:
    del window_seconds
    resolved_buckets = _normalize_buckets(buckets)
    if not resolved_buckets:
        return False

    client = await _require_redis_client(settings)
    resolved_limit = max(1, int(limit))
    try:
        counts = await client.mget([_rate_limit_key(bucket) for bucket in resolved_buckets])
    except Exception as exc:
        raise _auth_state_unavailable() from exc

    for raw_count in counts:
        if raw_count is None:
            continue
        try:
            if int(raw_count) >= resolved_limit:
                return True
        except (TypeError, ValueError):
            continue
    return False


async def record_failure(
    *,
    settings: Settings,
    buckets: Iterable[str],
    window_seconds: int,
) -> None:
    resolved_buckets = _normalize_buckets(buckets)
    if not resolved_buckets:
        return

    client = await _require_redis_client(settings)
    ttl_seconds = max(1, int(window_seconds))
    try:
        pipeline = client.pipeline()
        for bucket in resolved_buckets:
            pipeline.incr(_rate_limit_key(bucket))
        counts = await pipeline.execute()

        expiry_pipeline = client.pipeline()
        has_new_keys = False
        for bucket, raw_count in zip(resolved_buckets, counts, strict=False):
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count == 1:
                expiry_pipeline.expire(_rate_limit_key(bucket), ttl_seconds)
                has_new_keys = True
        if has_new_keys:
            await expiry_pipeline.execute()
    except Exception as exc:
        raise _auth_state_unavailable() from exc


async def clear_failures(*, settings: Settings, buckets: Iterable[str]) -> None:
    resolved_buckets = _normalize_buckets(buckets)
    if not resolved_buckets:
        return

    client = await _require_redis_client(settings)
    try:
        await client.delete(*[_rate_limit_key(bucket) for bucket in resolved_buckets])
    except Exception as exc:
        raise _auth_state_unavailable() from exc
