from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from jose import jwt

from tests.services.admin_auth_test_support import (
    RedisClient,
    admin_auth,
    admin_auth_state,
    reset_admin_auth_redis_client,
    settings_stub,
)

REFRESH_JTI = "refresh-jti-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
REFRESH_FAMILY_ID = "refresh-family-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def _reset_redis_client() -> None:
    reset_admin_auth_redis_client()


async def test_access_and_refresh_tokens_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_stub()
    client = RedisClient()

    async def _client(_settings: SimpleNamespace) -> RedisClient:
        return client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _client)

    access_token = admin_auth.build_access_token(
        settings=settings,
        email="Admin@Example.com",
        two_factor_verified=True,
    )
    refresh_token = admin_auth.build_refresh_token(
        settings=settings,
        email="Admin@Example.com",
        jti=REFRESH_JTI,
        family_id=REFRESH_FAMILY_ID,
    )

    access_payload = await admin_auth.decode_access_token(settings=settings, token=access_token)
    refresh_payload = await admin_auth.decode_refresh_token(settings=settings, token=refresh_token)

    assert access_payload is not None
    assert access_payload.email == "admin@example.com"
    assert access_payload.two_factor_verified is True
    assert refresh_payload is not None
    assert refresh_payload.email == "admin@example.com"
    assert refresh_payload.two_factor_verified is True
    assert refresh_payload.jti == REFRESH_JTI
    assert refresh_payload.family_id == REFRESH_FAMILY_ID


@pytest.mark.parametrize(
    "decoder", [admin_auth.decode_access_token, admin_auth.decode_refresh_token]
)
async def test_decode_token_rejects_empty_token(decoder) -> None:
    assert await decoder(settings=settings_stub(), token="") is None


async def test_decode_access_token_rejects_invalid_signature() -> None:
    token = admin_auth.build_access_token(
        settings=settings_stub(admin_jwt_secret="good-secret"),
        email="admin@example.com",
        two_factor_verified=False,
    )

    assert (
        await admin_auth.decode_access_token(
            settings=settings_stub(admin_jwt_secret="bad-secret"),
            token=token,
        )
        is None
    )


async def test_decode_refresh_token_rejects_invalid_signature() -> None:
    token = admin_auth.build_refresh_token(
        settings=settings_stub(admin_refresh_secret="good-secret"),
        email="admin@example.com",
        jti=REFRESH_JTI,
        family_id=REFRESH_FAMILY_ID,
    )

    assert (
        await admin_auth.decode_refresh_token(
            settings=settings_stub(admin_refresh_secret="bad-secret"),
            token=token,
        )
        is None
    )


async def test_decode_token_rejects_wrong_token_type() -> None:
    access_like_refresh = jwt.encode(
        {
            "sub": "admin@example.com",
            "role": "admin",
            "type": "refresh",
            "two_factor": True,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        settings_stub().admin_jwt_secret,
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
        settings_stub().admin_refresh_secret,
        algorithm="HS256",
    )

    assert (
        await admin_auth.decode_access_token(settings=settings_stub(), token=access_like_refresh)
        is None
    )
    assert (
        await admin_auth.decode_refresh_token(settings=settings_stub(), token=refresh_like_access)
        is None
    )


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"jti": REFRESH_JTI},
        {"family_id": REFRESH_FAMILY_ID},
        {"jti": "short", "family_id": REFRESH_FAMILY_ID},
        {"jti": REFRESH_JTI, "family_id": {"invalid": "type"}},
    ],
)
async def test_decode_refresh_token_rejects_legacy_or_invalid_session_identity(
    claims: dict[str, object],
) -> None:
    token = jwt.encode(
        {
            "sub": "admin@example.com",
            "role": "admin",
            "two_factor": True,
            "type": "refresh",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            **claims,
        },
        settings_stub().admin_refresh_secret,
        algorithm="HS256",
    )

    assert await admin_auth.decode_refresh_token(settings=settings_stub(), token=token) is None


@pytest.mark.parametrize(
    ("jti", "family_id"),
    [
        ("short", REFRESH_FAMILY_ID),
        (REFRESH_JTI, "contains spaces in family id"),
    ],
)
def test_build_refresh_token_rejects_invalid_session_identity(
    jti: str,
    family_id: str,
) -> None:
    with pytest.raises(admin_auth.AdminAuthError):
        admin_auth.build_refresh_token(
            settings=settings_stub(),
            email="admin@example.com",
            jti=jti,
            family_id=family_id,
        )


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
async def test_decode_access_token_rejects_missing_required_claims(
    payload: dict[str, object]
) -> None:
    token = jwt.encode(payload, settings_stub().admin_jwt_secret, algorithm="HS256")

    assert await admin_auth.decode_access_token(settings=settings_stub(), token=token) is None


async def test_revoke_access_token_blocklists_token(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RedisClient()
    token = admin_auth.build_access_token(
        settings=settings_stub(),
        email="admin@example.com",
        two_factor_verified=True,
    )

    async def _client(_settings: SimpleNamespace) -> RedisClient:
        return client

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _client)

    await admin_auth.revoke_access_token(settings=settings_stub(), token=token)

    assert client.set_calls[0]["key"] == admin_auth_state._revoked_token_key(token)
    assert client.set_calls[0]["value"] == "1"
    assert isinstance(client.set_calls[0]["ex"], int)
    assert client.set_calls[0]["ex"] >= 1
    assert await admin_auth.decode_access_token(settings=settings_stub(), token=token) is None


async def test_decode_access_token_raises_when_auth_state_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = admin_auth.build_access_token(
        settings=settings_stub(),
        email="admin@example.com",
        two_factor_verified=True,
    )

    async def _no_client(_settings: SimpleNamespace) -> None:
        return None

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _no_client)

    with pytest.raises(admin_auth.AdminAuthStateError):
        await admin_auth.decode_access_token(settings=settings_stub(), token=token)


async def test_decode_refresh_token_does_not_read_legacy_revocation_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = admin_auth.build_refresh_token(
        settings=settings_stub(),
        email="admin@example.com",
        jti=REFRESH_JTI,
        family_id=REFRESH_FAMILY_ID,
    )

    async def _unexpected_client(_settings: SimpleNamespace) -> None:
        raise AssertionError("refresh decode must not access Redis")

    monkeypatch.setattr(admin_auth_state, "_get_redis_client", _unexpected_client)

    payload = await admin_auth.decode_refresh_token(settings=settings_stub(), token=token)

    assert payload is not None
    assert payload.jti == REFRESH_JTI
    assert payload.family_id == REFRESH_FAMILY_ID
