from __future__ import annotations

import pytest

from app.services.admin import rate_limit
from tests.api.admin.admin_auth_test_support import settings_stub


class FakeRedis:
    def __init__(self) -> None:
        self._now = 0
        self._values: dict[str, tuple[int, int | None]] = {}

    async def mget(self, keys: list[str]) -> list[str | None]:
        self._expire()
        values: list[str | None] = []
        for key in keys:
            stored = self._values.get(key)
            values.append(None if stored is None else str(stored[0]))
        return values

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

    async def delete(self, *keys: str) -> int:
        self._expire()
        deleted = 0
        for key in keys:
            if self._values.pop(key, None) is not None:
                deleted += 1
        return deleted

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

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


class FakePipeline:
    def __init__(self, redis_client: FakeRedis) -> None:
        self._redis = redis_client
        self._commands: list[tuple[str, tuple[object, ...]]] = []

    def incr(self, key: str) -> FakePipeline:
        self._commands.append(("incr", (key,)))
        return self

    def expire(self, key: str, ttl_seconds: int) -> FakePipeline:
        self._commands.append(("expire", (key, ttl_seconds)))
        return self

    async def execute(self) -> list[object]:
        results: list[object] = []
        for command, args in self._commands:
            if command == "incr":
                results.append(await self._redis.incr(args[0]))  # type: ignore[arg-type]
                continue
            if command == "expire":
                results.append(await self._redis.expire(args[0], args[1]))  # type: ignore[arg-type]
        return results


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    redis_client = FakeRedis()

    async def _require_redis_client(settings):
        del settings
        return redis_client

    monkeypatch.setattr(rate_limit, "_require_redis_client", _require_redis_client)
    return redis_client


@pytest.mark.asyncio
async def test_is_rate_limited_returns_false_for_unknown_buckets(fake_redis: FakeRedis) -> None:
    assert (
        await rate_limit.is_rate_limited(
            settings=settings_stub(),
            buckets=("missing",),
            limit=3,
            window_seconds=60,
        )
        is False
    )
    assert fake_redis._values == {}


@pytest.mark.asyncio
async def test_record_failure_and_is_rate_limited_clamp_invalid_config(
    fake_redis: FakeRedis,
) -> None:
    await rate_limit.record_failure(
        settings=settings_stub(),
        buckets=("bucket",),
        window_seconds=0,
    )

    assert (
        await rate_limit.is_rate_limited(
            settings=settings_stub(),
            buckets=("bucket",),
            limit=0,
            window_seconds=0,
        )
        is True
    )


@pytest.mark.asyncio
async def test_is_rate_limited_detects_any_bucket_at_limit(fake_redis: FakeRedis) -> None:
    await rate_limit.record_failure(
        settings=settings_stub(),
        buckets=("bucket:ip", "bucket:email"),
        window_seconds=60,
    )
    await rate_limit.record_failure(
        settings=settings_stub(),
        buckets=("bucket:ip",),
        window_seconds=60,
    )

    assert (
        await rate_limit.is_rate_limited(
            settings=settings_stub(),
            buckets=("bucket:ip", "bucket:email"),
            limit=2,
            window_seconds=60,
        )
        is True
    )


@pytest.mark.asyncio
async def test_record_failure_uses_ttl_to_discard_expired_attempts(fake_redis: FakeRedis) -> None:
    await rate_limit.record_failure(
        settings=settings_stub(),
        buckets=("bucket",),
        window_seconds=1,
    )
    fake_redis.advance(2)

    assert (
        await rate_limit.is_rate_limited(
            settings=settings_stub(),
            buckets=("bucket",),
            limit=1,
            window_seconds=1,
        )
        is False
    )


@pytest.mark.asyncio
async def test_clear_failures_removes_existing_buckets_and_ignores_missing(
    fake_redis: FakeRedis,
) -> None:
    await rate_limit.record_failure(
        settings=settings_stub(),
        buckets=("bucket:ip", "bucket:email"),
        window_seconds=60,
    )

    await rate_limit.clear_failures(
        settings=settings_stub(),
        buckets=("bucket:ip", "bucket:email", "missing"),
    )

    assert fake_redis._values == {}
