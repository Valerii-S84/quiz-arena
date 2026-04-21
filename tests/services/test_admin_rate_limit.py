from __future__ import annotations

import pytest

from app.services.admin import rate_limit
from app.services.admin.auth_common import AdminAuthStateError
from tests.services.admin_auth_test_support import settings_stub as admin_settings_stub


class _RedisClientStub:
    def __init__(
        self,
        *,
        zcard_error: Exception | None = None,
        zadd_error: Exception | None = None,
        zremrange_error: Exception | None = None,
        expire_error: Exception | None = None,
        delete_error: Exception | None = None,
    ) -> None:
        self.values: dict[str, dict[str, float]] = {}
        self.zcard_error = zcard_error
        self.zadd_error = zadd_error
        self.zremrange_error = zremrange_error
        self.expire_error = expire_error
        self.delete_error = delete_error

    async def zremrangebyscore(self, key: str, _minimum: str, maximum: str) -> int:
        if self.zremrange_error is not None:
            raise self.zremrange_error
        members = self.values.get(key, {})
        if not members:
            return 0
        exclusive = maximum.startswith("(")
        cutoff = float(maximum[1:] if exclusive else maximum)
        removed = [
            member
            for member, score in members.items()
            if score < cutoff or (not exclusive and score <= cutoff)
        ]
        for member in removed:
            members.pop(member, None)
        if not members:
            self.values.pop(key, None)
        return len(removed)

    async def zcard(self, key: str) -> int:
        if self.zcard_error is not None:
            raise self.zcard_error
        return len(self.values.get(key, {}))

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        if self.zadd_error is not None:
            raise self.zadd_error
        self.values.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        if self.expire_error is not None:
            raise self.expire_error
        assert seconds >= 1
        return key in self.values

    async def delete(self, key: str) -> int:
        if self.delete_error is not None:
            raise self.delete_error
        return int(self.values.pop(key, None) is not None)


@pytest.fixture
def redis_client(monkeypatch: pytest.MonkeyPatch) -> _RedisClientStub:
    client = _RedisClientStub()

    async def _client(_settings) -> _RedisClientStub:
        return client

    monkeypatch.setattr(rate_limit, "require_redis_client", _client)
    return client


async def test_is_rate_limited_returns_false_for_unknown_bucket(
    redis_client: _RedisClientStub,
) -> None:
    settings = admin_settings_stub()

    assert (
        await rate_limit.is_rate_limited(
            settings=settings,
            bucket="missing",
            limit=3,
            window_seconds=60,
        )
        is False
    )
    assert redis_client.values == {}


async def test_record_failure_and_is_rate_limited_clamp_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
    redis_client: _RedisClientStub,
) -> None:
    settings = admin_settings_stub()
    times = iter([100.0, 100.0])
    monkeypatch.setattr(rate_limit.time, "time", lambda: next(times))

    await rate_limit.record_failure(settings=settings, bucket="bucket", window_seconds=0)

    assert (
        await rate_limit.is_rate_limited(
            settings=settings,
            bucket="bucket",
            limit=0,
            window_seconds=0,
        )
        is True
    )
    assert list(next(iter(redis_client.values.values())).values()) == [100.0]


async def test_is_rate_limited_discards_expired_attempts(
    monkeypatch: pytest.MonkeyPatch,
    redis_client: _RedisClientStub,
) -> None:
    settings = admin_settings_stub()
    key = rate_limit._bucket_key("bucket")
    redis_client.values[key] = {"old": 10.0}
    monkeypatch.setattr(rate_limit.time, "time", lambda: 12.1)

    assert (
        await rate_limit.is_rate_limited(
            settings=settings,
            bucket="bucket",
            limit=1,
            window_seconds=1,
        )
        is False
    )
    assert key not in redis_client.values


async def test_clear_failures_removes_existing_bucket_and_ignores_missing(
    redis_client: _RedisClientStub,
) -> None:
    settings = admin_settings_stub()
    key = rate_limit._bucket_key("bucket")
    redis_client.values[key] = {"attempt": 1.0}

    await rate_limit.clear_failures(settings=settings, bucket="bucket")
    await rate_limit.clear_failures(settings=settings, bucket="missing")

    assert redis_client.values == {}


async def test_record_failure_raises_when_redis_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = admin_settings_stub()
    client = _RedisClientStub(zadd_error=RuntimeError("boom"))

    async def _client(_settings) -> _RedisClientStub:
        return client

    monkeypatch.setattr(rate_limit, "require_redis_client", _client)
    monkeypatch.setattr(rate_limit.time, "time", lambda: 100.0)

    with pytest.raises(AdminAuthStateError):
        await rate_limit.record_failure(settings=settings, bucket="bucket", window_seconds=60)


async def test_is_rate_limited_raises_when_state_store_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = admin_settings_stub()

    async def _down(_settings) -> _RedisClientStub:
        raise AdminAuthStateError("down")

    monkeypatch.setattr(rate_limit, "require_redis_client", _down)

    with pytest.raises(AdminAuthStateError):
        await rate_limit.is_rate_limited(
            settings=settings,
            bucket="bucket",
            limit=3,
            window_seconds=60,
        )
