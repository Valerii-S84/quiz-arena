from __future__ import annotations

from app.core.config import Settings
from app.services.admin.cache import get_redis_client

CONTACT_RATE_LIMIT_KEY_PREFIX = "qa_contact:rate_limit:"


class ContactRateLimitStateError(RuntimeError):
    pass


def _contact_rate_limit_key(bucket: str) -> str:
    return f"{CONTACT_RATE_LIMIT_KEY_PREFIX}{bucket}"


def _state_unavailable() -> ContactRateLimitStateError:
    return ContactRateLimitStateError("Contact rate limit state store is unavailable")


async def consume_contact_submission_slot(
    *,
    settings: Settings,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> bool:
    client = await get_redis_client(settings)
    if client is None:
        raise _state_unavailable()

    resolved_limit = max(1, int(limit))
    ttl_seconds = max(1, int(window_seconds))
    key = _contact_rate_limit_key(bucket)
    try:
        count = await client.incr(key)
        ttl_seconds_remaining = await client.ttl(key)
        if int(count) == 1 or int(ttl_seconds_remaining) < 0:
            await client.expire(key, ttl_seconds)
    except Exception as exc:
        raise _state_unavailable() from exc
    return int(count) > resolved_limit
