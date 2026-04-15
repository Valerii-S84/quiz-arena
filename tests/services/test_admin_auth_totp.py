from __future__ import annotations

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

    async def _missing_secret(_settings: SimpleNamespace, *, strict: bool = False) -> str:
        del strict
        return ""

    async def _store_secret(
        *, settings: SimpleNamespace, secret: str, strict: bool = False
    ) -> None:
        del settings, strict
        stored.append(secret)

    monkeypatch.setattr(admin_auth_totp, "get_totp_secret", _missing_secret)
    monkeypatch.setattr(admin_auth_totp, "set_totp_secret", _store_secret)

    payload = await admin_auth.get_totp_setup_payload(settings=settings_stub())

    assert payload["secret"] == stored[0]
    assert "otpauth://" in payload["otpauth_uri"]


async def test_get_totp_setup_payload_reuses_existing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    async def _existing_secret(_settings: SimpleNamespace, *, strict: bool = False) -> str:
        del strict
        return "existing-secret"

    async def _unexpected_store(
        *, settings: SimpleNamespace, secret: str, strict: bool = False
    ) -> None:
        del settings, strict
        called.append(secret)

    monkeypatch.setattr(admin_auth_totp, "get_totp_secret", _existing_secret)
    monkeypatch.setattr(admin_auth_totp, "set_totp_secret", _unexpected_store)

    payload = await admin_auth.get_totp_setup_payload(settings=settings_stub())

    assert payload["secret"] == "existing-secret"
    assert called == []


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


async def test_set_totp_secret_is_noop_for_env_secret_missing_client_and_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RedisClient()

    async def _unexpected_client(_settings: SimpleNamespace) -> RedisClient:
        return client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _unexpected_client)
    await admin_auth.set_totp_secret(
        settings=settings_stub(admin_totp_secret="configured"),
        secret="new-secret",
    )
    assert client.set_calls == []

    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _no_client)
    await admin_auth.set_totp_secret(settings=settings_stub(), secret="new-secret")

    failing_client = RedisClient(set_error=RuntimeError("boom"))

    async def _failing_client(_settings: SimpleNamespace) -> RedisClient:
        return failing_client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _failing_client)
    await admin_auth.set_totp_secret(settings=settings_stub(), secret="new-secret")


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
