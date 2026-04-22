from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth
from app.api.routes.admin import deps as admin_deps
from app.main import app
from tests.api.admin.admin_auth_login_test_support import (
    ADMIN_AUTH,
    ADMIN_RATE_LIMIT,
    AUTH_HELPERS,
    login_buckets,
    verify_buckets,
)
from tests.api.admin.admin_auth_test_support import principal_stub, settings_stub


def test_admin_login_rejects_invalid_credentials(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[tuple[tuple[str, ...], int]] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: False)
    monkeypatch.setattr(
        ADMIN_RATE_LIMIT,
        "record_failure",
        lambda *, settings, buckets, window_seconds: failures.append(
            (tuple(buckets), window_seconds)
        ),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_INVALID_CREDENTIALS"}}
    assert failures == [(login_buckets().keys, 300)]


def test_admin_login_rejects_rate_limited_requests(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: True)

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "E_RATE_LIMITED"}}


def test_admin_login_returns_503_when_rate_limit_state_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_state_error(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _raise_state_error)

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_login_returns_503_when_record_failure_store_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_state_error(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "record_failure", _raise_state_error)

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_verify_2fa_rejects_rate_limited_requests(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(
        AUTH_HELPERS, "verify_2fa_rate_limit_buckets", lambda **kwargs: verify_buckets()
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: True)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "E_RATE_LIMITED"}}


def test_admin_verify_2fa_returns_503_when_rate_limit_state_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_state_error(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(
        AUTH_HELPERS, "verify_2fa_rate_limit_buckets", lambda **kwargs: verify_buckets()
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _raise_state_error)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_verify_2fa_rejects_invalid_code(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[tuple[tuple[str, ...], int]] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(
        AUTH_HELPERS, "verify_2fa_rate_limit_buckets", lambda **kwargs: verify_buckets()
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(
        ADMIN_RATE_LIMIT,
        "record_failure",
        lambda *, settings, buckets, window_seconds: failures.append(
            (tuple(buckets), window_seconds)
        ),
    )

    async def _false_totp(**kwargs) -> bool:
        del kwargs
        return False

    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _false_totp)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_INVALID_TOTP"}}
    assert failures == [(verify_buckets().keys, 300)]


def test_admin_verify_2fa_returns_503_when_record_failure_store_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_state_error(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    async def _false_totp(**kwargs) -> bool:
        del kwargs
        return False

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(
        AUTH_HELPERS, "verify_2fa_rate_limit_buckets", lambda **kwargs: verify_buckets()
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _false_totp)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "record_failure", _raise_state_error)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_verify_2fa_returns_503_when_auth_state_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _error_totp(**kwargs) -> bool:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(
        AUTH_HELPERS, "verify_2fa_rate_limit_buckets", lambda **kwargs: verify_buckets()
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _error_totp)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
