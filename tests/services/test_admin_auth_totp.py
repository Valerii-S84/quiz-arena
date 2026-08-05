from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pyotp
import pytest

from tests.services.admin_auth_test_support import (
    RedisClient,
    admin_auth,
    admin_auth_state,
    admin_auth_totp,
    reset_admin_auth_redis_client,
    settings_stub,
)


@pytest.fixture(autouse=True)
def _reset_redis_client() -> None:
    reset_admin_auth_redis_client()


async def test_get_totp_setup_payload_generates_secret_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: list[str] = []

    async def _store_secret(
        *, settings: SimpleNamespace, secret: str, strict: bool = False
    ) -> bool:
        del settings, strict
        stored.append(secret)
        return True

    monkeypatch.setattr(admin_auth_totp, "set_totp_secret", _store_secret)

    payload = await admin_auth.get_totp_setup_payload(settings=settings_stub())

    assert payload is not None
    assert payload["secret"] == stored[0]
    assert "otpauth://" in payload["otpauth_uri"]


async def test_get_totp_setup_payload_denies_existing_enrollment() -> None:
    payload = await admin_auth.get_totp_setup_payload(
        settings=settings_stub(admin_totp_secret="existing-secret")
    )

    assert payload is None


async def test_get_totp_setup_payload_has_one_concurrent_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []
    stored_secret: str | None = None
    both_ready = asyncio.Event()

    async def _store_once(*, settings: SimpleNamespace, secret: str, strict: bool = False) -> bool:
        nonlocal stored_secret
        del settings, strict
        attempts.append(secret)
        if len(attempts) == 2:
            both_ready.set()
        await both_ready.wait()
        if stored_secret is not None:
            return False
        stored_secret = secret
        return True

    monkeypatch.setattr(admin_auth_totp, "set_totp_secret", _store_once)

    results = await asyncio.gather(
        admin_auth.get_totp_setup_payload(settings=settings_stub()),
        admin_auth.get_totp_setup_payload(settings=settings_stub()),
    )

    winners = [payload for payload in results if payload is not None]
    assert len(winners) == 1
    assert winners[0]["secret"] == stored_secret
    assert len(set(attempts)) == 2


async def test_verify_totp_code_rejects_missing_blank_and_invalid_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _missing_secret(_settings: SimpleNamespace, *, strict: bool = False) -> str:
        del strict
        return ""

    monkeypatch.setattr(admin_auth_totp, "get_totp_secret", _missing_secret)
    assert await admin_auth.verify_totp_code(settings=settings_stub(), code="123456") is False

    secret = pyotp.random_base32()

    async def _secret(_settings: SimpleNamespace, *, strict: bool = False) -> str:
        del strict
        return secret

    monkeypatch.setattr(admin_auth_totp, "get_totp_secret", _secret)
    assert await admin_auth.verify_totp_code(settings=settings_stub(), code="   ") is False

    valid_code = pyotp.TOTP(secret).now()
    invalid_code = f"{(int(valid_code[0]) + 1) % 10}{valid_code[1:]}"
    assert await admin_auth.verify_totp_code(settings=settings_stub(), code=invalid_code) is False


async def test_verify_totp_code_accepts_current_code(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = pyotp.random_base32()

    async def _secret(_settings: SimpleNamespace, *, strict: bool = False) -> str:
        del strict
        return secret

    monkeypatch.setattr(admin_auth_totp, "get_totp_secret", _secret)

    assert (
        await admin_auth.verify_totp_code(
            settings=settings_stub(),
            code=pyotp.TOTP(secret).now(),
        )
        is True
    )


async def test_get_totp_setup_payload_raises_when_state_store_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _no_client)

    with pytest.raises(admin_auth.AdminAuthStateError):
        await admin_auth.get_totp_setup_payload(settings=settings_stub())


async def test_verify_totp_code_raises_when_state_store_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _no_client)

    with pytest.raises(admin_auth.AdminAuthStateError):
        await admin_auth.verify_totp_code(settings=settings_stub(), code="123456")


async def test_get_totp_secret_prefers_env_secret() -> None:
    assert await admin_auth.get_totp_secret(settings_stub(admin_totp_secret=" env-secret ")) == (
        "env-secret"
    )


async def test_get_totp_secret_returns_trimmed_string_from_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RedisClient(get_value=" redis-secret ")

    async def _client(_settings: SimpleNamespace) -> RedisClient:
        return client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _client)

    assert await admin_auth.get_totp_secret(settings_stub()) == "redis-secret"


async def test_get_totp_secret_returns_empty_for_missing_client_and_redis_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _no_client)
    assert await admin_auth.get_totp_secret(settings_stub()) == ""

    client = RedisClient(get_error=RuntimeError("boom"))

    async def _error_client(_settings: SimpleNamespace) -> RedisClient:
        return client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _error_client)
    assert await admin_auth.get_totp_secret(settings_stub()) == ""

    bytes_client = RedisClient(get_value=b"secret")

    async def _bytes_client(_settings: SimpleNamespace) -> RedisClient:
        return bytes_client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _bytes_client)
    assert await admin_auth.get_totp_secret(settings_stub()) == ""


async def test_set_totp_secret_rejects_env_secret_missing_client_and_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RedisClient()

    async def _unexpected_client(_settings: SimpleNamespace) -> RedisClient:
        return client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _unexpected_client)
    assert (
        await admin_auth.set_totp_secret(
            settings=settings_stub(admin_totp_secret="configured"),
            secret="new-secret",
        )
        is False
    )
    assert client.set_calls == []

    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _no_client)
    assert await admin_auth.set_totp_secret(settings=settings_stub(), secret="new-secret") is False

    class _FailingClient:
        async def set(self, key: str, value: str, *, nx: bool = False) -> bool:
            del key, value, nx
            raise RuntimeError("boom")

    async def _failing_client(_settings: SimpleNamespace) -> _FailingClient:
        return _FailingClient()

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _failing_client)
    assert await admin_auth.set_totp_secret(settings=settings_stub(), secret="new-secret") is False


async def test_set_totp_secret_uses_set_nx_and_reports_the_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    results: list[bool | None] = [True, None]

    class _Client:
        async def set(self, key: str, value: str, *, nx: bool = False) -> bool | None:
            calls.append({"key": key, "value": value, "nx": nx})
            return results.pop(0)

    client = _Client()

    async def _client(_settings: SimpleNamespace) -> _Client:
        return client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _client)

    winner_enrolled = await admin_auth.set_totp_secret(
        settings=settings_stub(),
        secret="winner-secret",
        strict=True,
    )
    loser_enrolled = await admin_auth.set_totp_secret(
        settings=settings_stub(),
        secret="loser-secret",
        strict=True,
    )

    assert winner_enrolled is True
    assert loser_enrolled is False
    assert calls == [
        {
            "key": admin_auth_state._ADMIN_TOTP_SECRET_KEY,
            "value": "winner-secret",
            "nx": True,
        },
        {
            "key": admin_auth_state._ADMIN_TOTP_SECRET_KEY,
            "value": "loser-secret",
            "nx": True,
        },
    ]


async def test_get_redis_client_caches_successful_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RedisClient()
    created: list[str] = []

    def _from_url(url: str, *, encoding: str, decode_responses: bool) -> RedisClient:
        created.append(url)
        assert encoding == "utf-8"
        assert decode_responses is True
        return client

    monkeypatch.setattr(admin_auth_state.redis, "from_url", _from_url)
    settings = settings_stub(redis_url="redis://cache")

    first = await admin_auth_state._get_redis_client(settings)
    second = await admin_auth_state._get_redis_client(settings)

    assert first is client
    assert second is client
    assert created == ["redis://cache"]


async def test_get_redis_client_recreates_client_after_event_loop_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    class _Client(RedisClient):
        def __init__(self, label: str) -> None:
            super().__init__()
            self.label = label

        async def aclose(self) -> None:
            closed.append(self.label)

    loop_one = object()
    loop_two = object()
    current_loop = loop_one
    first_client = _Client("first")
    second_client = _Client("second")
    created = [first_client, second_client]

    monkeypatch.setattr(admin_auth_state.asyncio, "get_running_loop", lambda: current_loop)
    monkeypatch.setattr(
        admin_auth_state.redis,
        "from_url",
        lambda *args, **kwargs: created.pop(0),
    )
    settings = settings_stub(redis_url="redis://cache")

    first = await admin_auth_state._get_redis_client(settings)
    current_loop = loop_two
    second = await admin_auth_state._get_redis_client(settings)

    assert first is first_client
    assert second is second_client
    assert closed == ["first"]


async def test_get_redis_client_returns_none_on_ping_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RedisClient(ping_error=RuntimeError("down"))
    monkeypatch.setattr(admin_auth_state.redis, "from_url", lambda *args, **kwargs: client)

    assert await admin_auth_state._get_redis_client(settings_stub()) is None
    assert admin_auth_state._redis_client is None
