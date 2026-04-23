from __future__ import annotations

import pytest

from app.services import contact_rate_limit
from tests.api.admin.admin_auth_test_support import settings_stub


class FakeRedis:
    def __init__(self) -> None:
        self._now = 0
        self._values: dict[str, tuple[int, int | None]] = {}

    async def incr(self, key: str) -> int:
        self._expire()
        value, expires_at = self._values.get(key, (0, None))
        next_value = value + 1
        self._values[key] = (next_value, expires_at)
        return next_value

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        self._expire()
        if key not in self._values:
            return False
        value, _ = self._values[key]
        self._values[key] = (value, self._now + ttl_seconds)
        return True

    async def ttl(self, key: str) -> int:
        self._expire()
        stored = self._values.get(key)
        if stored is None:
            return -2
        _, expires_at = stored
        if expires_at is None:
            return -1
        return expires_at - self._now

    def advance(self, seconds: int) -> None:
        self._now += seconds
        self._expire()

    def _expire(self) -> None:
        expired = [
            key
            for key, (_, expires_at) in self._values.items()
            if expires_at is not None and expires_at <= self._now
        ]
        for key in expired:
            self._values.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    redis_client = FakeRedis()

    async def _get_redis_client(settings):
        del settings
        return redis_client

    monkeypatch.setattr(contact_rate_limit, "get_redis_client", _get_redis_client)
    return redis_client


@pytest.mark.asyncio
async def test_consume_contact_submission_slot_rearms_missing_ttl(
    fake_redis: FakeRedis,
) -> None:
    bucket = "contact:ip:127.0.0.1"
    key = contact_rate_limit._contact_rate_limit_key(bucket)
    fake_redis._values[key] = (4, None)

    is_rate_limited = await contact_rate_limit.consume_contact_submission_slot(
        settings=settings_stub(),
        bucket=bucket,
        limit=10,
        window_seconds=3,
    )

    assert is_rate_limited is False
    assert await fake_redis.ttl(key) == 3

    fake_redis.advance(4)

    assert key not in fake_redis._values
