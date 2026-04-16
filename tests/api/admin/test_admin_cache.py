from __future__ import annotations

import pytest

from app.services.admin import cache as admin_cache
from tests.type_helpers import build_settings


def _settings():
    return build_settings(redis_url="redis://test")


@pytest.fixture(autouse=True)
def _reset_cached_client() -> None:
    admin_cache._redis_client = None
    admin_cache._redis_client_loop_id = None


@pytest.mark.asyncio
async def test_get_json_cache_handles_missing_client_empty_payload_and_get_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _none_client(settings):
        del settings
        return None

    monkeypatch.setattr(admin_cache, "get_redis_client", _none_client)
    assert await admin_cache.get_json_cache(settings=_settings(), key="cache-key") is None

    class _BrokenClient:
        async def get(self, key: str) -> str:
            del key
            raise RuntimeError("boom")

    async def _broken_client(settings):
        del settings
        return _BrokenClient()

    monkeypatch.setattr(admin_cache, "get_redis_client", _broken_client)
    assert await admin_cache.get_json_cache(settings=_settings(), key="cache-key") is None

    class _EmptyClient:
        async def get(self, key: str) -> str:
            del key
            return ""

    async def _empty_client(settings):
        del settings
        return _EmptyClient()

    monkeypatch.setattr(admin_cache, "get_redis_client", _empty_client)
    assert await admin_cache.get_json_cache(settings=_settings(), key="cache-key") is None


@pytest.mark.asyncio
async def test_get_json_cache_handles_invalid_json_and_non_dict_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, payload: str) -> None:
            self.payload = payload

        async def get(self, key: str) -> str:
            del key
            return self.payload

    async def _invalid_json(settings):
        del settings
        return _Client("{invalid")

    monkeypatch.setattr(admin_cache, "get_redis_client", _invalid_json)
    assert await admin_cache.get_json_cache(settings=_settings(), key="cache-key") is None

    async def _non_dict(settings):
        del settings
        return _Client('["x"]')

    monkeypatch.setattr(admin_cache, "get_redis_client", _non_dict)
    assert await admin_cache.get_json_cache(settings=_settings(), key="cache-key") is None


@pytest.mark.asyncio
async def test_get_redis_client_recreates_client_after_event_loop_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    class _Client:
        def __init__(self, label: str) -> None:
            self.label = label

        async def ping(self) -> None:
            return None

        async def aclose(self) -> None:
            closed.append(self.label)

    loop_one = object()
    loop_two = object()
    current_loop = loop_one
    first_client = _Client("first")
    second_client = _Client("second")
    created = [first_client, second_client]

    monkeypatch.setattr(admin_cache.asyncio, "get_running_loop", lambda: current_loop)
    monkeypatch.setattr(admin_cache.redis, "from_url", lambda *args, **kwargs: created.pop(0))

    first = await admin_cache.get_redis_client(_settings())
    current_loop = loop_two
    second = await admin_cache.get_redis_client(_settings())

    assert first is first_client
    assert second is second_client
    assert closed == ["first"]


@pytest.mark.asyncio
async def test_set_json_cache_handles_missing_client_and_set_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _none_client(settings):
        del settings
        return None

    monkeypatch.setattr(admin_cache, "get_redis_client", _none_client)
    await admin_cache.set_json_cache(
        settings=_settings(),
        key="cache-key",
        value={"v": 1},
        ttl_seconds=0,
    )

    class _BrokenClient:
        async def set(self, key: str, value: str, ex: int) -> None:
            del key, value, ex
            raise RuntimeError("boom")

    async def _broken_client(settings):
        del settings
        return _BrokenClient()

    monkeypatch.setattr(admin_cache, "get_redis_client", _broken_client)
    await admin_cache.set_json_cache(
        settings=_settings(),
        key="cache-key",
        value={"v": 1},
        ttl_seconds=0,
    )
