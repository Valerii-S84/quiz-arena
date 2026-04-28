from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any, cast

import pytest

from app.core.config import Settings
from app.services import ops_auth
from tests.type_helpers import build_settings


class _FakeRedis:
    def __init__(
        self,
        *,
        set_results: list[bool] | None = None,
        existing_keys: set[str] | None = None,
    ) -> None:
        self.set_results = set_results or [True]
        self.existing_keys = existing_keys or set()
        self.set_calls: list[tuple[str, str, int, bool]] = []
        self.deleted_keys: list[str] = []

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        self.set_calls.append((key, value, ex, nx))
        return self.set_results.pop(0)

    async def exists(self, key: str) -> int:
        return int(key in self.existing_keys)

    async def delete(self, key: str) -> int:
        self.deleted_keys.append(key)
        self.existing_keys.discard(key)
        return 1


def _settings() -> Settings:
    return build_settings(redis_url="redis://unused-for-tests")


def _redis_provider(client: object):
    async def _require_redis_client(_settings):
        return client

    return _require_redis_client


@pytest.fixture(autouse=True)
def _reset_cached_redis() -> Generator[None, None, None]:
    ops_auth._redis_client = None
    ops_auth._redis_client_loop_id = None
    yield
    ops_auth._redis_client = None
    ops_auth._redis_client_loop_id = None


@pytest.mark.asyncio
async def test_issue_ops_ui_session_stores_unique_session_with_minimum_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis(set_results=[False, True])
    issued_tokens = iter(["collision", "fresh"])

    async def _require_redis_client(settings):
        assert settings.redis_url == "redis://unused-for-tests"
        return client

    monkeypatch.setattr(ops_auth, "_require_redis_client", _require_redis_client)
    monkeypatch.setattr(ops_auth.secrets, "token_urlsafe", lambda _size: next(issued_tokens))

    session_id = await ops_auth.issue_ops_ui_session(settings=_settings(), ttl_seconds=0)

    assert session_id == "fresh"
    assert client.set_calls == [
        ("qa_ops_ui:session:collision", "1", 1, True),
        ("qa_ops_ui:session:fresh", "1", 1, True),
    ]


@pytest.mark.asyncio
async def test_issue_ops_ui_session_raises_when_unique_id_cannot_be_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis(set_results=[False, False, False])
    monkeypatch.setattr(ops_auth, "_require_redis_client", _redis_provider(client))
    monkeypatch.setattr(ops_auth.secrets, "token_urlsafe", lambda _size: "collision")

    with pytest.raises(ops_auth.OpsSessionStateError) as exc_info:
        await ops_auth.issue_ops_ui_session(settings=_settings(), ttl_seconds=60)

    assert str(exc_info.value) == "Failed to issue a unique ops session id"


@pytest.mark.asyncio
async def test_validate_ops_ui_session_returns_false_without_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _require_redis_client(_settings):
        raise AssertionError("redis should not be required for a missing session id")

    monkeypatch.setattr(ops_auth, "_require_redis_client", _require_redis_client)

    assert await ops_auth.validate_ops_ui_session(settings=_settings(), session_id=None) is False
    assert await ops_auth.validate_ops_ui_session(settings=_settings(), session_id="") is False


@pytest.mark.asyncio
async def test_validate_ops_ui_session_checks_server_side_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis(existing_keys={"qa_ops_ui:session:active"})
    monkeypatch.setattr(ops_auth, "_require_redis_client", _redis_provider(client))

    assert await ops_auth.validate_ops_ui_session(settings=_settings(), session_id="active") is True
    assert (
        await ops_auth.validate_ops_ui_session(settings=_settings(), session_id="expired") is False
    )


@pytest.mark.asyncio
async def test_revoke_ops_ui_session_deletes_server_side_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis(existing_keys={"qa_ops_ui:session:active"})
    monkeypatch.setattr(ops_auth, "_require_redis_client", _redis_provider(client))

    await ops_auth.revoke_ops_ui_session(settings=_settings(), session_id="active")

    assert client.deleted_keys == ["qa_ops_ui:session:active"]
    assert client.existing_keys == set()


@pytest.mark.asyncio
async def test_revoke_ops_ui_session_ignores_missing_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _require_redis_client(_settings):
        raise AssertionError("redis should not be required for a missing session id")

    monkeypatch.setattr(ops_auth, "_require_redis_client", _require_redis_client)

    await ops_auth.revoke_ops_ui_session(settings=_settings(), session_id=None)


@pytest.mark.asyncio
async def test_require_redis_client_raises_when_store_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _get_redis_client(_settings):
        return None

    monkeypatch.setattr(ops_auth, "_get_redis_client", _get_redis_client)

    with pytest.raises(ops_auth.OpsSessionStateError) as exc_info:
        await ops_auth._require_redis_client(_settings())

    assert str(exc_info.value) == "Ops session state store is unavailable"


@pytest.mark.asyncio
async def test_require_redis_client_returns_available_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()

    async def _get_redis_client(_settings):
        return client

    monkeypatch.setattr(ops_auth, "_get_redis_client", _get_redis_client)

    assert await ops_auth._require_redis_client(_settings()) is client


@pytest.mark.asyncio
async def test_redis_operation_errors_map_to_session_state_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRedis:
        async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
            raise OSError("redis down")

        async def exists(self, key: str) -> int:
            raise OSError("redis down")

        async def delete(self, key: str) -> int:
            raise OSError("redis down")

    client = FailingRedis()
    monkeypatch.setattr(ops_auth, "_require_redis_client", _redis_provider(client))

    with pytest.raises(ops_auth.OpsSessionStateError):
        await ops_auth.issue_ops_ui_session(settings=_settings(), ttl_seconds=60)
    with pytest.raises(ops_auth.OpsSessionStateError):
        await ops_auth.validate_ops_ui_session(settings=_settings(), session_id="active")
    with pytest.raises(ops_auth.OpsSessionStateError):
        await ops_auth.revoke_ops_ui_session(settings=_settings(), session_id="active")


@pytest.mark.asyncio
async def test_get_redis_client_reuses_client_for_current_loop_and_closes_stale_loop_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_clients: list[Any] = []

    class RedisFromUrlClient:
        def __init__(self) -> None:
            self.closed = False

        async def ping(self) -> None:
            return None

        async def aclose(self) -> None:
            self.closed = True

    def _from_url(redis_url: str, *, encoding: str, decode_responses: bool):
        assert redis_url == "redis://unused-for-tests"
        assert encoding == "utf-8"
        assert decode_responses is True
        client = RedisFromUrlClient()
        created_clients.append(client)
        return client

    monkeypatch.setattr(ops_auth.redis, "from_url", _from_url)

    first_client = await ops_auth._get_redis_client(_settings())
    second_client = await ops_auth._get_redis_client(_settings())

    assert first_client is second_client
    assert len(created_clients) == 1

    ops_auth._redis_client_loop_id = id(asyncio.get_running_loop()) + 1
    third_client = await ops_auth._get_redis_client(_settings())

    assert third_client is not first_client
    assert created_clients[0].closed is True
    assert len(created_clients) == 2


@pytest.mark.asyncio
async def test_get_redis_client_swallows_stale_close_error_and_ping_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StaleRedisClient:
        async def aclose(self) -> None:
            raise OSError("close failed")

    class FailingPingClient:
        async def ping(self) -> None:
            raise OSError("redis down")

    ops_auth._redis_client = cast(Any, StaleRedisClient())
    ops_auth._redis_client_loop_id = id(asyncio.get_running_loop()) + 1
    monkeypatch.setattr(
        ops_auth.redis,
        "from_url",
        lambda _redis_url, *, encoding, decode_responses: FailingPingClient(),
    )

    assert await ops_auth._get_redis_client(_settings()) is None
    assert ops_auth._redis_client is None
    assert ops_auth._redis_client_loop_id is None
