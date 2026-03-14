from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp
import pytest
from jose import jwt

from app.services.admin import auth as admin_auth


class _CookieResponse:
    def __init__(self) -> None:
        self.set_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []

    def set_cookie(self, **kwargs: object) -> None:
        self.set_calls.append(kwargs)

    def delete_cookie(self, **kwargs: object) -> None:
        self.delete_calls.append(kwargs)


class _RedisClient:
    def __init__(
        self,
        *,
        get_value: object = None,
        get_error: Exception | None = None,
        set_error: Exception | None = None,
        ping_error: Exception | None = None,
    ) -> None:
        self.get_value = get_value
        self.get_error = get_error
        self.set_error = set_error
        self.ping_error = ping_error
        self.set_calls: list[tuple[str, str]] = []

    async def ping(self) -> None:
        if self.ping_error is not None:
            raise self.ping_error

    async def get(self, key: str) -> object:
        if self.get_error is not None:
            raise self.get_error
        assert key == "qa_admin:totp_secret"
        return self.get_value

    async def set(self, key: str, value: str) -> None:
        if self.set_error is not None:
            raise self.set_error
        self.set_calls.append((key, value))


@pytest.fixture(autouse=True)
def _reset_redis_client() -> None:
    admin_auth._redis_client = None


def _settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "app_env": "test",
        "admin_email": "admin@example.com",
        "admin_password_hash": "",
        "admin_password_plain": "secret123",
        "admin_jwt_secret": "jwt-secret",
        "admin_refresh_secret": "refresh-secret",
        "admin_totp_secret": "",
        "admin_totp_issuer": "Quiz Arena Admin",
        "admin_access_token_ttl_minutes": 15,
        "admin_refresh_token_ttl_days": 7,
        "redis_url": "redis://localhost:6379/15",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_get_password_hash_rejects_missing_configuration() -> None:
    settings = _settings(admin_password_hash="", admin_password_plain=" ")

    with pytest.raises(admin_auth.AdminAuthError):
        admin_auth._get_password_hash(settings)


def test_get_password_hash_builds_fallback_hash_from_plain_password() -> None:
    password_hash = admin_auth._get_password_hash(
        _settings(admin_password_hash="", admin_password_plain="secret123")
    )

    assert admin_auth._pwd_context.verify("secret123", password_hash) is True


def test_verify_login_credentials_requires_matching_email_and_password() -> None:
    password_hash = admin_auth._pwd_context.hash("secret123")
    settings = _settings(admin_password_hash=password_hash, admin_password_plain="")

    assert (
        admin_auth.verify_login_credentials(
            settings=settings,
            email="ADMIN@example.com",
            password="secret123",
        )
        is True
    )
    assert (
        admin_auth.verify_login_credentials(
            settings=settings,
            email="viewer@example.com",
            password="secret123",
        )
        is False
    )
    assert (
        admin_auth.verify_login_credentials(
            settings=settings,
            email="admin@example.com",
            password="wrong",
        )
        is False
    )


def test_access_and_refresh_tokens_round_trip() -> None:
    settings = _settings()

    access_token = admin_auth.build_access_token(
        settings=settings,
        email="Admin@Example.com",
        two_factor_verified=True,
    )
    refresh_token = admin_auth.build_refresh_token(settings=settings, email="Admin@Example.com")

    access_payload = admin_auth.decode_access_token(settings=settings, token=access_token)
    refresh_payload = admin_auth.decode_refresh_token(settings=settings, token=refresh_token)

    assert access_payload is not None
    assert access_payload.email == "admin@example.com"
    assert access_payload.two_factor_verified is True
    assert refresh_payload is not None
    assert refresh_payload.email == "admin@example.com"
    assert refresh_payload.two_factor_verified is True


@pytest.mark.parametrize(
    "decoder", [admin_auth.decode_access_token, admin_auth.decode_refresh_token]
)
def test_decode_token_rejects_empty_token(decoder) -> None:
    assert decoder(settings=_settings(), token="") is None


def test_decode_access_token_rejects_invalid_signature() -> None:
    token = admin_auth.build_access_token(
        settings=_settings(admin_jwt_secret="good-secret"),
        email="admin@example.com",
        two_factor_verified=False,
    )

    assert (
        admin_auth.decode_access_token(
            settings=_settings(admin_jwt_secret="bad-secret"), token=token
        )
        is None
    )


def test_decode_refresh_token_rejects_invalid_signature() -> None:
    token = admin_auth.build_refresh_token(
        settings=_settings(admin_refresh_secret="good-secret"),
        email="admin@example.com",
    )

    assert (
        admin_auth.decode_refresh_token(
            settings=_settings(admin_refresh_secret="bad-secret"),
            token=token,
        )
        is None
    )


def test_decode_token_rejects_wrong_token_type() -> None:
    access_like_refresh = jwt.encode(
        {
            "sub": "admin@example.com",
            "role": "admin",
            "type": "refresh",
            "two_factor": True,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        _settings().admin_jwt_secret,
        algorithm="HS256",
    )
    refresh_like_access = jwt.encode(
        {
            "sub": "admin@example.com",
            "role": "admin",
            "type": "access",
            "two_factor": True,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        _settings().admin_refresh_secret,
        algorithm="HS256",
    )

    assert admin_auth.decode_access_token(settings=_settings(), token=access_like_refresh) is None
    assert admin_auth.decode_refresh_token(settings=_settings(), token=refresh_like_access) is None


@pytest.mark.parametrize(
    "payload",
    [
        {
            "sub": "",
            "role": "admin",
            "type": "access",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        {
            "sub": "admin@example.com",
            "role": "",
            "type": "access",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        {"sub": "admin@example.com", "role": "admin", "type": "access", "exp": "bad"},
    ],
)
def test_decode_access_token_rejects_missing_required_claims(payload: dict[str, object]) -> None:
    token = jwt.encode(payload, _settings().admin_jwt_secret, algorithm="HS256")

    assert admin_auth.decode_access_token(settings=_settings(), token=token) is None


async def test_get_totp_setup_payload_generates_secret_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: list[str] = []

    async def _missing_secret(_settings: SimpleNamespace) -> str:
        return ""

    async def _store_secret(*, settings: SimpleNamespace, secret: str) -> None:
        del settings
        stored.append(secret)

    monkeypatch.setattr(admin_auth, "get_totp_secret", _missing_secret)
    monkeypatch.setattr(admin_auth, "set_totp_secret", _store_secret)

    payload = await admin_auth.get_totp_setup_payload(settings=_settings())

    assert payload["secret"] == stored[0]
    assert "otpauth://" in payload["otpauth_uri"]


async def test_get_totp_setup_payload_reuses_existing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    async def _existing_secret(_settings: SimpleNamespace) -> str:
        return "existing-secret"

    async def _unexpected_store(*, settings: SimpleNamespace, secret: str) -> None:
        del settings
        called.append(secret)

    monkeypatch.setattr(admin_auth, "get_totp_secret", _existing_secret)
    monkeypatch.setattr(admin_auth, "set_totp_secret", _unexpected_store)

    payload = await admin_auth.get_totp_setup_payload(settings=_settings())

    assert payload["secret"] == "existing-secret"
    assert called == []


async def test_verify_totp_code_rejects_missing_blank_and_invalid_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _missing_secret(_settings: SimpleNamespace) -> str:
        return ""

    monkeypatch.setattr(admin_auth, "get_totp_secret", _missing_secret)
    assert await admin_auth.verify_totp_code(settings=_settings(), code="123456") is False

    secret = pyotp.random_base32()

    async def _secret(_settings: SimpleNamespace) -> str:
        return secret

    monkeypatch.setattr(admin_auth, "get_totp_secret", _secret)
    assert await admin_auth.verify_totp_code(settings=_settings(), code="   ") is False

    valid_code = pyotp.TOTP(secret).now()
    invalid_code = f"{(int(valid_code[0]) + 1) % 10}{valid_code[1:]}"
    assert await admin_auth.verify_totp_code(settings=_settings(), code=invalid_code) is False


async def test_verify_totp_code_accepts_current_code(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = pyotp.random_base32()

    async def _secret(_settings: SimpleNamespace) -> str:
        return secret

    monkeypatch.setattr(admin_auth, "get_totp_secret", _secret)

    assert (
        await admin_auth.verify_totp_code(
            settings=_settings(),
            code=pyotp.TOTP(secret).now(),
        )
        is True
    )


async def test_get_totp_secret_prefers_env_secret() -> None:
    assert (
        await admin_auth.get_totp_secret(_settings(admin_totp_secret=" env-secret "))
        == "env-secret"
    )


async def test_get_totp_secret_returns_trimmed_string_from_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RedisClient(get_value=" redis-secret ")

    async def _client(_settings: SimpleNamespace) -> _RedisClient:
        return client

    monkeypatch.setattr(admin_auth, "_get_redis_client", _client)

    assert await admin_auth.get_totp_secret(_settings()) == "redis-secret"


async def test_get_totp_secret_returns_empty_for_missing_client_and_redis_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth, "_get_redis_client", _no_client)
    assert await admin_auth.get_totp_secret(_settings()) == ""

    client = _RedisClient(get_error=RuntimeError("boom"))

    async def _error_client(_settings: SimpleNamespace) -> _RedisClient:
        return client

    monkeypatch.setattr(admin_auth, "_get_redis_client", _error_client)
    assert await admin_auth.get_totp_secret(_settings()) == ""

    bytes_client = _RedisClient(get_value=b"secret")

    async def _bytes_client(_settings: SimpleNamespace) -> _RedisClient:
        return bytes_client

    monkeypatch.setattr(admin_auth, "_get_redis_client", _bytes_client)
    assert await admin_auth.get_totp_secret(_settings()) == ""


async def test_set_totp_secret_is_noop_for_env_secret_missing_client_and_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RedisClient()

    async def _unexpected_client(_settings: SimpleNamespace) -> _RedisClient:
        return client

    monkeypatch.setattr(admin_auth, "_get_redis_client", _unexpected_client)
    await admin_auth.set_totp_secret(
        settings=_settings(admin_totp_secret="configured"), secret="new-secret"
    )
    assert client.set_calls == []

    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth, "_get_redis_client", _no_client)
    await admin_auth.set_totp_secret(settings=_settings(), secret="new-secret")

    failing_client = _RedisClient(set_error=RuntimeError("boom"))

    async def _failing_client(_settings: SimpleNamespace) -> _RedisClient:
        return failing_client

    monkeypatch.setattr(admin_auth, "_get_redis_client", _failing_client)
    await admin_auth.set_totp_secret(settings=_settings(), secret="new-secret")


async def test_get_redis_client_caches_successful_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _RedisClient()
    created: list[str] = []

    def _from_url(url: str, *, encoding: str, decode_responses: bool) -> _RedisClient:
        created.append(url)
        assert encoding == "utf-8"
        assert decode_responses is True
        return client

    monkeypatch.setattr(admin_auth.redis, "from_url", _from_url)
    settings = _settings(redis_url="redis://cache")

    first = await admin_auth._get_redis_client(settings)
    second = await admin_auth._get_redis_client(settings)

    assert first is client
    assert second is client
    assert created == ["redis://cache"]


async def test_get_redis_client_returns_none_on_ping_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _RedisClient(ping_error=RuntimeError("down"))
    monkeypatch.setattr(admin_auth.redis, "from_url", lambda *args, **kwargs: client)

    assert await admin_auth._get_redis_client(_settings()) is None
    assert admin_auth._redis_client is None


def test_auth_cookie_helpers_set_and_clear_expected_cookies() -> None:
    response = _CookieResponse()
    settings = _settings(
        app_env="prod",
        admin_access_token_ttl_minutes=0,
        admin_refresh_token_ttl_days=0,
    )

    admin_auth.apply_auth_cookies(
        settings=settings,
        response=response,
        access_token="access-token",
        refresh_token="refresh-token",
    )
    admin_auth.clear_auth_cookies(response)

    assert response.set_calls == [
        {
            "key": admin_auth.ADMIN_ACCESS_COOKIE,
            "value": "access-token",
            "max_age": 60,
            "httponly": True,
            "samesite": "strict",
            "secure": True,
            "path": "/",
        },
        {
            "key": admin_auth.ADMIN_REFRESH_COOKIE,
            "value": "refresh-token",
            "max_age": 60,
            "httponly": True,
            "samesite": "strict",
            "secure": True,
            "path": "/",
        },
    ]
    assert response.delete_calls == [
        {"key": admin_auth.ADMIN_ACCESS_COOKIE, "path": "/"},
        {"key": admin_auth.ADMIN_REFRESH_COOKIE, "path": "/"},
    ]
