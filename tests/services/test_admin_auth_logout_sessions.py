from __future__ import annotations

import asyncio

import pytest

from app.services.admin import auth_refresh_sessions, auth_state, auth_tokens
from tests.services.admin_auth_test_support import settings_stub


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}
        self.eval_calls: list[tuple[str, int, tuple[object, ...]]] = []
        self.eval_error: Exception | None = None
        self._eval_lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def eval(self, script: str, key_count: int, *args: object) -> int:
        async with self._eval_lock:
            self.eval_calls.append((script, key_count, args))
            if self.eval_error is not None:
                raise self.eval_error
            if script == auth_refresh_sessions._REVOKE_LOGOUT_SESSION_SCRIPT:
                self._apply_logout(args)
                return 1
            if script == auth_refresh_sessions._ROTATE_REFRESH_SESSION_SCRIPT:
                return self._apply_rotation(args)
            raise AssertionError("unexpected Redis script")

    def _apply_logout(self, args: tuple[object, ...]) -> None:
        (
            access_key,
            family_key,
            has_access,
            access_ttl,
            has_refresh,
            refresh_ttl,
            revoked_state,
        ) = (str(value) for value in args)
        if has_access == "1":
            self.values[access_key] = "1"
            self.expiries[access_key] = int(access_ttl)
        if has_refresh == "1":
            ttl = self.expiries.get(family_key, int(refresh_ttl))
            self.values[family_key] = revoked_state
            self.expiries[family_key] = ttl

    def _apply_rotation(self, args: tuple[object, ...]) -> int:
        family_key, predecessor, successor, revoked, ttl = (str(value) for value in args)
        current = self.values.get(family_key)
        if current is None:
            return 2
        if current == revoked:
            return 3
        if current != predecessor:
            self.values[family_key] = revoked
            return 4
        self.values[family_key] = successor
        self.expiries[family_key] = int(ttl)
        return 1


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, object]]] = []

    def warning(self, event: str, **payload: object) -> None:
        self.warnings.append((event, payload))


def _identity(label: str) -> auth_refresh_sessions.RefreshSessionIdentity:
    return auth_refresh_sessions.RefreshSessionIdentity(
        family_id=f"family-{label}",
        jti=f"jti-{label}",
    )


def _seed_family(client: _FakeRedis, identity: auth_refresh_sessions.RefreshSessionIdentity) -> str:
    family_key = auth_refresh_sessions._refresh_family_key(identity.family_id)
    client.values[family_key] = auth_refresh_sessions._active_session_state(identity.jti)
    client.expiries[family_key] = 321
    return family_key


def _install_client(monkeypatch: pytest.MonkeyPatch, client: _FakeRedis) -> None:
    async def _client(_settings):
        return client

    monkeypatch.setattr(auth_refresh_sessions, "_require_redis_client", _client)
    monkeypatch.setattr(auth_state, "_require_redis_client", _client)


async def test_logout_atomically_revokes_access_copy_and_current_refresh_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_stub()
    access_token = auth_tokens.build_access_token(
        settings=settings,
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
    )
    access_revocation = auth_tokens.resolve_access_token_revocation(
        settings=settings,
        token=access_token,
    )
    assert access_revocation is not None
    refresh_identity = _identity("logout")
    client = _FakeRedis()
    family_key = _seed_family(client, refresh_identity)
    _install_client(monkeypatch, client)

    await auth_refresh_sessions.revoke_logout_session(
        settings=settings,
        access_revocation=access_revocation,
        refresh_family_id=refresh_identity.family_id,
    )

    assert len(client.eval_calls) == 1
    assert client.eval_calls[0][1] == 2
    assert client.values[access_revocation.key] == "1"
    assert client.values[family_key] == auth_refresh_sessions._REVOKED_STATE
    assert client.expiries[family_key] == 321
    assert await auth_tokens.decode_access_token(settings=settings, token=access_token) is None
    rotation = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings,
        family_id=refresh_identity.family_id,
        jti=refresh_identity.jti,
    )
    assert rotation.status is auth_refresh_sessions.RefreshRotationStatus.REVOKED


async def test_logout_without_valid_identities_is_idempotent_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_client(_settings):
        raise AssertionError("Redis must not be required without identities")

    monkeypatch.setattr(auth_refresh_sessions, "_require_redis_client", _unexpected_client)

    await auth_refresh_sessions.revoke_logout_session(
        settings=settings_stub(),
        access_revocation=None,
        refresh_family_id=None,
    )


async def test_logout_and_refresh_rotation_have_one_serialized_family_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_stub()
    predecessor = _identity("race")
    client = _FakeRedis()
    family_key = _seed_family(client, predecessor)
    _install_client(monkeypatch, client)

    _, rotation = await asyncio.gather(
        auth_refresh_sessions.revoke_logout_session(
            settings=settings,
            access_revocation=None,
            refresh_family_id=predecessor.family_id,
        ),
        auth_refresh_sessions.rotate_refresh_session(
            settings=settings,
            family_id=predecessor.family_id,
            jti=predecessor.jti,
        ),
    )

    assert client.values[family_key] == auth_refresh_sessions._REVOKED_STATE
    assert rotation.status in {
        auth_refresh_sessions.RefreshRotationStatus.ROTATED,
        auth_refresh_sessions.RefreshRotationStatus.REVOKED,
    }
    if rotation.session is not None:
        successor = await auth_refresh_sessions.rotate_refresh_session(
            settings=settings,
            family_id=rotation.session.family_id,
            jti=rotation.session.jti,
        )
        assert successor.status is auth_refresh_sessions.RefreshRotationStatus.REVOKED


async def test_logout_redis_failure_logs_bounded_event_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_stub()
    access_token = auth_tokens.build_access_token(
        settings=settings,
        email="secret-admin@example.com",
        role="admin",
        two_factor_verified=True,
    )
    access_revocation = auth_tokens.resolve_access_token_revocation(
        settings=settings,
        token=access_token,
    )
    assert access_revocation is not None
    family_id = "family-secret-logout"
    client = _FakeRedis()
    client.eval_error = RuntimeError("redis down")
    logger = _Logger()
    _install_client(monkeypatch, client)
    monkeypatch.setattr(auth_refresh_sessions, "logger", logger)

    with pytest.raises(auth_refresh_sessions.AdminAuthStateError):
        await auth_refresh_sessions.revoke_logout_session(
            settings=settings,
            access_revocation=access_revocation,
            refresh_family_id=family_id,
        )

    assert logger.warnings == [
        (
            "admin_logout_revocation_failed",
            {"reason": "state_store_unavailable"},
        )
    ]
    serialized_logs = str(logger.warnings)
    assert access_token not in serialized_logs
    assert family_id not in serialized_logs
