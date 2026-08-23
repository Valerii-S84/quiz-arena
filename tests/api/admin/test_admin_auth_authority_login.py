from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth
from app.api.routes.admin import deps as admin_deps
from app.main import app
from app.services.admin import auth_authority
from tests.api.admin.admin_auth_login_test_support import (
    ADMIN_AUTH,
    ADMIN_RATE_LIMIT,
    AUTH_HELPERS,
    login_buckets,
    verify_buckets,
)
from tests.api.admin.admin_auth_test_support import authority_stub, principal_stub, settings_stub

AUTH_REFRESH_SESSIONS = auth.auth_refresh_sessions


def _prepare_valid_login(monkeypatch: pytest.MonkeyPatch, *, two_fa_required: bool) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(
        two_fa_required=two_fa_required
    )
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "clear_failures", lambda **kwargs: None)


def _unexpected_issuer(calls: list[str], name: str):
    def _call(**kwargs):
        del kwargs
        calls.append(name)
        return "unexpected"

    return _call


def test_login_without_2fa_issues_only_database_authority_claims(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    authority = authority_stub(email="admin@example.com", role="super_admin")

    async def _resolve(**kwargs) -> auth_authority.CurrentAdminAuthority:
        assert kwargs == {"email": "admin@example.com"}
        order.append("resolve")
        return authority

    async def _create_refresh(**kwargs):
        del kwargs
        order.append("create_family")
        return AUTH_REFRESH_SESSIONS.RefreshSessionIdentity(
            family_id="refresh-family-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            jti="refresh-jti-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )

    def _build_access(**kwargs) -> str:
        assert kwargs["email"] == authority.email
        assert kwargs["role"] == authority.role
        order.append("build_access")
        return "access"

    def _build_refresh(**kwargs) -> str:
        assert kwargs["email"] == authority.email
        assert kwargs["role"] == authority.role
        order.append("build_refresh")
        return "refresh"

    _prepare_valid_login(monkeypatch, two_fa_required=False)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _resolve)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _create_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _build_access)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _build_refresh)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "apply_auth_cookies",
        lambda **kwargs: order.append("cookies"),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert order == ["resolve", "create_family", "build_access", "build_refresh", "cookies"]


def test_login_with_2fa_issues_partial_claims_only_from_database_authority(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    authority = authority_stub(email="admin@example.com", role="super_admin")

    async def _resolve(**kwargs) -> auth_authority.CurrentAdminAuthority:
        del kwargs
        order.append("resolve")
        return authority

    def _build_access(**kwargs) -> str:
        assert kwargs["email"] == authority.email
        assert kwargs["role"] == authority.role
        assert kwargs["two_factor_verified"] is False
        order.append("build_access")
        return "partial"

    _prepare_valid_login(monkeypatch, two_fa_required=True)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _resolve)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _build_access)
    monkeypatch.setattr(
        AUTH_HELPERS,
        "set_partial_access_cookie",
        lambda **kwargs: order.append("cookie"),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert order == ["resolve", "build_access", "cookie"]


@pytest.mark.parametrize("two_fa_required", [True, False])
def test_login_denies_missing_disabled_or_mismatched_authority_before_issuance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    two_fa_required: bool,
) -> None:
    calls: list[str] = []

    async def _deny(**kwargs):
        del kwargs
        return None

    async def _unexpected_refresh(**kwargs):
        del kwargs
        calls.append("refresh_family")
        return None

    _prepare_valid_login(monkeypatch, two_fa_required=two_fa_required)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _deny)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _unexpected_refresh)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_access_token",
        _unexpected_issuer(calls, "access"),
    )
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_refresh_token",
        _unexpected_issuer(calls, "refresh"),
    )
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _unexpected_issuer(calls, "cookies"))
    monkeypatch.setattr(
        AUTH_HELPERS,
        "set_partial_access_cookie",
        _unexpected_issuer(calls, "partial_cookie"),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_INVALID_CREDENTIALS"}}
    assert calls == []


@pytest.mark.parametrize("two_fa_required", [True, False])
def test_login_authority_outage_returns_503_before_issuance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    two_fa_required: bool,
) -> None:
    calls: list[str] = []

    async def _outage(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    async def _unexpected_refresh(**kwargs):
        del kwargs
        calls.append("refresh_family")
        return None

    _prepare_valid_login(monkeypatch, two_fa_required=two_fa_required)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _outage)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _unexpected_refresh)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_access_token",
        _unexpected_issuer(calls, "access"),
    )
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_refresh_token",
        _unexpected_issuer(calls, "refresh"),
    )
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _unexpected_issuer(calls, "cookies"))
    monkeypatch.setattr(
        AUTH_HELPERS,
        "set_partial_access_cookie",
        _unexpected_issuer(calls, "partial_cookie"),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert calls == []


def test_login_denies_invalid_configured_bootstrap_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    invalid_settings = settings_stub(two_fa_required=False).model_copy(
        update={"admin_role": "owner"}
    )
    app.dependency_overrides[auth.get_settings] = lambda: invalid_settings
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: True)

    async def _unexpected_resolver(**kwargs):
        del kwargs
        calls.append("resolver")
        return authority_stub()

    async def _unexpected_refresh(**kwargs):
        del kwargs
        calls.append("refresh_family")
        return None

    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _unexpected_resolver)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _unexpected_refresh)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_access_token",
        _unexpected_issuer(calls, "access"),
    )
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_refresh_token",
        _unexpected_issuer(calls, "refresh"),
    )
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _unexpected_issuer(calls, "cookies"))
    monkeypatch.setattr(
        AUTH_HELPERS,
        "set_partial_access_cookie",
        _unexpected_issuer(calls, "partial_cookie"),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 401
    assert calls == []


def test_2fa_completion_rechecks_authority_before_full_issuance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _valid_totp(**kwargs) -> bool:
        del kwargs
        return True

    async def _deny(**kwargs):
        del kwargs
        return None

    async def _unexpected_refresh(**kwargs):
        del kwargs
        calls.append("refresh_family")
        return None

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub()
    monkeypatch.setattr(
        AUTH_HELPERS,
        "verify_2fa_rate_limit_buckets",
        lambda **kwargs: verify_buckets(),
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _valid_totp)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _deny)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _unexpected_refresh)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_access_token",
        _unexpected_issuer(calls, "access"),
    )
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_refresh_token",
        _unexpected_issuer(calls, "refresh"),
    )
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _unexpected_issuer(calls, "cookies"))

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_UNAUTHORIZED"}}
    assert calls == []


def test_2fa_completion_authority_outage_returns_503_before_full_issuance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _valid_totp(**kwargs) -> bool:
        del kwargs
        return True

    async def _outage(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    async def _unexpected_refresh(**kwargs):
        del kwargs
        calls.append("refresh_family")
        return None

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub()
    monkeypatch.setattr(
        AUTH_HELPERS,
        "verify_2fa_rate_limit_buckets",
        lambda **kwargs: verify_buckets(),
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _valid_totp)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _outage)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _unexpected_refresh)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_access_token",
        _unexpected_issuer(calls, "access"),
    )
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_refresh_token",
        _unexpected_issuer(calls, "refresh"),
    )
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _unexpected_issuer(calls, "cookies"))

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert calls == []
