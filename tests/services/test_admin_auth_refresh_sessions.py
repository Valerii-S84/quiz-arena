from __future__ import annotations

import asyncio

import pytest

from app.services.admin import auth_refresh_sessions
from tests.services.admin_auth_test_support import settings_stub


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}
        self.set_calls: list[dict[str, object]] = []
        self.eval_calls: list[tuple[object, ...]] = []
        self.set_error: Exception | None = None
        self.eval_error: Exception | None = None
        self._eval_lock = asyncio.Lock()

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int,
        nx: bool = False,
    ) -> bool:
        self.set_calls.append({"key": key, "value": value, "ex": ex, "nx": nx})
        if self.set_error is not None:
            raise self.set_error
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expiries[key] = ex
        return True

    async def eval(
        self,
        script: str,
        key_count: int,
        family_key: str,
        predecessor_state: str,
        successor_state: str,
        revoked_state: str,
        ttl_seconds: str,
    ) -> object:
        async with self._eval_lock:
            call = (
                script,
                key_count,
                family_key,
                predecessor_state,
                successor_state,
                revoked_state,
                ttl_seconds,
            )
            self.eval_calls.append(call)
            if self.eval_error is not None:
                raise self.eval_error

            current = self.values.get(family_key)
            if current is None:
                return 2
            if current == revoked_state:
                return 3
            if current != predecessor_state:
                self.values[family_key] = revoked_state
                return 4

            self.values[family_key] = successor_state
            self.expiries[family_key] = int(ttl_seconds)
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


def _seed_active(
    client: _FakeRedis,
    identity: auth_refresh_sessions.RefreshSessionIdentity,
    *,
    ttl_seconds: int = 123,
) -> str:
    key = auth_refresh_sessions._refresh_family_key(identity.family_id)
    client.values[key] = auth_refresh_sessions._active_session_state(identity.jti)
    client.expiries[key] = ttl_seconds
    return key


def _install_client(monkeypatch: pytest.MonkeyPatch, client: _FakeRedis) -> None:
    async def _client(_settings):
        return client

    monkeypatch.setattr(auth_refresh_sessions, "_require_redis_client", _client)


async def test_create_refresh_session_uses_nx_and_bounded_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()
    _install_client(monkeypatch, client)

    session = await auth_refresh_sessions.create_refresh_session(
        settings=settings_stub(admin_refresh_token_ttl_days=0)
    )

    assert session.family_id
    assert session.jti
    assert session.family_id != session.jti
    assert client.set_calls == [
        {
            "key": auth_refresh_sessions._refresh_family_key(session.family_id),
            "value": auth_refresh_sessions._active_session_state(session.jti),
            "ex": 24 * 60 * 60,
            "nx": True,
        }
    ]


async def test_rotate_refresh_session_replaces_active_predecessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()
    predecessor = _identity("predecessor")
    family_key = _seed_active(client, predecessor)
    _install_client(monkeypatch, client)

    result = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings_stub(admin_refresh_token_ttl_days=2),
        family_id=predecessor.family_id,
        jti=predecessor.jti,
    )

    assert result.status is auth_refresh_sessions.RefreshRotationStatus.ROTATED
    assert result.session is not None
    assert result.session.family_id == predecessor.family_id
    assert result.session.jti != predecessor.jti
    assert client.values[family_key] == auth_refresh_sessions._active_session_state(
        result.session.jti
    )
    assert client.expiries[family_key] == 2 * 24 * 60 * 60
    assert client.eval_calls[0][1] == 1
    assert client.eval_calls[0][2] == family_key


async def test_predecessor_replay_revokes_family_and_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()
    predecessor = _identity("predecessor")
    family_key = _seed_active(client, predecessor)
    _install_client(monkeypatch, client)
    settings = settings_stub()

    winner = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings,
        family_id=predecessor.family_id,
        jti=predecessor.jti,
    )
    replay = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings,
        family_id=predecessor.family_id,
        jti=predecessor.jti,
    )

    assert winner.session is not None
    assert replay.status is auth_refresh_sessions.RefreshRotationStatus.REPLAY
    assert client.values[family_key] == auth_refresh_sessions._REVOKED_STATE
    successor = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings,
        family_id=winner.session.family_id,
        jti=winner.session.jti,
    )
    assert successor.status is auth_refresh_sessions.RefreshRotationStatus.REVOKED


async def test_two_concurrent_rotations_have_one_winner_and_revoke_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()
    predecessor = _identity("concurrent")
    family_key = _seed_active(client, predecessor)
    _install_client(monkeypatch, client)

    async def _rotate() -> auth_refresh_sessions.RefreshRotationResult:
        return await auth_refresh_sessions.rotate_refresh_session(
            settings=settings_stub(),
            family_id=predecessor.family_id,
            jti=predecessor.jti,
        )

    results = await asyncio.gather(_rotate(), _rotate())

    assert {result.status for result in results} == {
        auth_refresh_sessions.RefreshRotationStatus.ROTATED,
        auth_refresh_sessions.RefreshRotationStatus.REPLAY,
    }
    assert sum(result.session is not None for result in results) == 1
    assert client.values[family_key] == auth_refresh_sessions._REVOKED_STATE


@pytest.mark.parametrize(
    ("stored_state", "expected_status"),
    [
        (None, auth_refresh_sessions.RefreshRotationStatus.MISSING),
        (
            auth_refresh_sessions._REVOKED_STATE,
            auth_refresh_sessions.RefreshRotationStatus.REVOKED,
        ),
    ],
)
async def test_rotate_refresh_session_rejects_missing_or_revoked_family(
    monkeypatch: pytest.MonkeyPatch,
    stored_state: str | None,
    expected_status: auth_refresh_sessions.RefreshRotationStatus,
) -> None:
    client = _FakeRedis()
    identity = _identity("unavailable")
    if stored_state is not None:
        client.values[auth_refresh_sessions._refresh_family_key(identity.family_id)] = stored_state
    _install_client(monkeypatch, client)

    result = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings_stub(),
        family_id=identity.family_id,
        jti=identity.jti,
    )

    assert result.status is expected_status
    assert result.session is None


async def test_stale_session_replay_tombstones_family(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedis()
    active = _identity("active")
    stale = auth_refresh_sessions.RefreshSessionIdentity(
        family_id=active.family_id,
        jti="jti-stale",
    )
    family_key = _seed_active(client, active)
    _install_client(monkeypatch, client)

    result = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings_stub(),
        family_id=stale.family_id,
        jti=stale.jti,
    )

    assert result.status is auth_refresh_sessions.RefreshRotationStatus.REPLAY
    assert client.values[family_key] == auth_refresh_sessions._REVOKED_STATE


async def test_create_refresh_session_maps_redis_failure_to_state_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()
    client.set_error = RuntimeError("redis down")
    _install_client(monkeypatch, client)

    with pytest.raises(auth_refresh_sessions.AdminAuthStateError):
        await auth_refresh_sessions.create_refresh_session(settings=settings_stub())


async def test_rotate_refresh_session_maps_redis_failure_to_state_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()
    identity = _identity("outage")
    _seed_active(client, identity)
    client.eval_error = RuntimeError("redis down")
    _install_client(monkeypatch, client)

    with pytest.raises(auth_refresh_sessions.AdminAuthStateError):
        await auth_refresh_sessions.rotate_refresh_session(
            settings=settings_stub(),
            family_id=identity.family_id,
            jti=identity.jti,
        )


async def test_replay_logging_contains_no_refresh_session_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()
    active = _identity("active-secret")
    family_key = _seed_active(client, active)
    client.values[family_key] = auth_refresh_sessions._active_session_state("different-jti")
    logger = _Logger()
    _install_client(monkeypatch, client)
    monkeypatch.setattr(auth_refresh_sessions, "logger", logger)
    result = await auth_refresh_sessions.rotate_refresh_session(
        settings=settings_stub(),
        family_id=active.family_id,
        jti=active.jti,
    )

    assert result.status is auth_refresh_sessions.RefreshRotationStatus.REPLAY
    assert logger.warnings == [
        (
            "admin_refresh_session_replay_detected",
            {"reason": "predecessor_or_stale_session"},
        )
    ]
    serialized_logs = str(logger.warnings)
    assert active.family_id not in serialized_logs
    assert active.jti not in serialized_logs
