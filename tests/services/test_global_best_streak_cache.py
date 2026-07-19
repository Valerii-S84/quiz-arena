from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core import global_best_streak_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expiries[key] = ex

    async def eval(self, script: str, key_count: int, key: str, value: str, ttl: str) -> int:
        del script, key_count
        current = int(self.values.get(key, "-1"))
        candidate = int(value)
        if candidate > current:
            self.values[key] = str(candidate)
            self.expiries[key] = int(ttl)
            return candidate
        return current

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        redis_url="redis://test",
        global_best_streak_cache_ttl_seconds=45,
    )


@pytest.fixture(autouse=True)
def _reset_local_cache() -> None:
    global_best_streak_cache._local_best_streak = None
    global_best_streak_cache._local_best_streak_expires_at = 0.0
    global_best_streak_cache._local_lock = None
    global_best_streak_cache._local_lock_loop_id = None


@pytest.mark.asyncio
async def test_get_global_best_streak_uses_cached_value(monkeypatch) -> None:
    fake = _FakeRedis()
    fake.values[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] = "27"

    async def _unexpected_db_lookup(*_args, **_kwargs):
        pytest.fail("cached global best should not query the database")

    async def _fake_client(settings):
        del settings
        return fake

    monkeypatch.setattr(global_best_streak_cache, "get_settings", _settings)
    monkeypatch.setattr(global_best_streak_cache, "_get_redis_client", _fake_client)
    monkeypatch.setattr(
        global_best_streak_cache.UsersRepo,
        "get_global_best_streak",
        _unexpected_db_lookup,
    )

    session = cast(AsyncSession, object())
    assert await global_best_streak_cache.get_global_best_streak(session) == 27


@pytest.mark.asyncio
async def test_get_global_best_streak_fills_cache_on_miss(monkeypatch) -> None:
    fake = _FakeRedis()

    session = cast(AsyncSession, object())

    async def _db_lookup(db_session: AsyncSession) -> int:
        assert db_session is session
        return 31

    async def _fake_client(settings):
        del settings
        return fake

    monkeypatch.setattr(global_best_streak_cache, "get_settings", _settings)
    monkeypatch.setattr(global_best_streak_cache, "_get_redis_client", _fake_client)
    monkeypatch.setattr(global_best_streak_cache.UsersRepo, "get_global_best_streak", _db_lookup)

    assert await global_best_streak_cache.get_global_best_streak(session) == 31
    assert fake.values[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] == "31"
    assert fake.expiries[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] == 45


@pytest.mark.asyncio
async def test_maybe_update_global_best_streak_only_raises_cached_value(monkeypatch) -> None:
    fake = _FakeRedis()
    fake.values[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] = "20"

    async def _fake_client(settings):
        del settings
        return fake

    monkeypatch.setattr(global_best_streak_cache, "get_settings", _settings)
    monkeypatch.setattr(global_best_streak_cache, "_get_redis_client", _fake_client)

    await global_best_streak_cache.maybe_update_global_best_streak(19)
    assert fake.values[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] == "20"

    await global_best_streak_cache.maybe_update_global_best_streak(25)
    assert fake.values[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] == "25"
    assert fake.expiries[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] == 45


@pytest.mark.asyncio
async def test_maybe_update_global_best_streak_caches_redis_winner(monkeypatch) -> None:
    fake = _FakeRedis()
    fake.values[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] = "30"

    async def _fake_client(settings):
        del settings
        return fake

    monkeypatch.setattr(global_best_streak_cache, "get_settings", _settings)
    monkeypatch.setattr(global_best_streak_cache, "_get_redis_client", _fake_client)

    await global_best_streak_cache.maybe_update_global_best_streak(25)

    assert fake.values[global_best_streak_cache.GLOBAL_BEST_STREAK_CACHE_KEY] == "30"
    assert global_best_streak_cache._get_local_best_streak() == 30


@pytest.mark.asyncio
async def test_schedule_global_best_streak_update_waits_for_commit(monkeypatch) -> None:
    calls: list[int] = []

    async def _fake_update(best_streak: int) -> None:
        calls.append(best_streak)

    monkeypatch.setattr(
        global_best_streak_cache,
        "maybe_update_global_best_streak",
        _fake_update,
    )
    sync_session = Session()
    sync_session.begin()
    session = SimpleNamespace(sync_session=sync_session)

    global_best_streak_cache.schedule_global_best_streak_update_after_commit(
        cast(AsyncSession, session),
        18,
    )
    global_best_streak_cache.schedule_global_best_streak_update_after_commit(
        cast(AsyncSession, session),
        21,
    )

    assert calls == []
    sync_session.commit()
    await asyncio.sleep(0)
    assert calls == [21]


@pytest.mark.asyncio
async def test_schedule_global_best_streak_update_drops_rollback(monkeypatch) -> None:
    calls: list[int] = []

    async def _fake_update(best_streak: int) -> None:
        calls.append(best_streak)

    monkeypatch.setattr(
        global_best_streak_cache,
        "maybe_update_global_best_streak",
        _fake_update,
    )
    sync_session = Session()
    sync_session.begin()
    session = SimpleNamespace(sync_session=sync_session)

    global_best_streak_cache.schedule_global_best_streak_update_after_commit(
        cast(AsyncSession, session),
        18,
    )

    sync_session.rollback()
    await asyncio.sleep(0)
    assert calls == []
