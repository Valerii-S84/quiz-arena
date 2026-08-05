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

AUTH_REFRESH_SESSIONS = auth.auth_refresh_sessions


def _refresh_session() -> AUTH_REFRESH_SESSIONS.RefreshSessionIdentity:
    return AUTH_REFRESH_SESSIONS.RefreshSessionIdentity(
        family_id="refresh-family-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        jti="refresh-jti-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )


def test_admin_login_without_2fa_sets_full_auth_cookies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cookie_calls: list[dict[str, str]] = []
    cleared: list[tuple[str, ...]] = []
    order: list[str] = []

    async def _create_refresh_session(**kwargs) -> AUTH_REFRESH_SESSIONS.RefreshSessionIdentity:
        del kwargs
        order.append("create_family")
        return _refresh_session()

    def _build_access(**kwargs) -> str:
        del kwargs
        order.append("build_access")
        return "access-token"

    def _build_refresh(**kwargs) -> str:
        assert kwargs["jti"] == _refresh_session().jti
        assert kwargs["family_id"] == _refresh_session().family_id
        order.append("build_refresh")
        return "refresh-token"

    def _apply_cookies(**kwargs) -> None:
        order.append("apply_cookies")
        cookie_calls.append(
            {
                "access_token": kwargs["access_token"],
                "refresh_token": kwargs["refresh_token"],
            }
        )

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=False)
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(
        ADMIN_RATE_LIMIT,
        "clear_failures",
        lambda *, settings, buckets: cleared.append(tuple(buckets)),
    )
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _create_refresh_session)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _build_access)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _build_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _apply_cookies)

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": False}
    assert cleared == [login_buckets().keys]
    assert cookie_calls == [{"access_token": "access-token", "refresh_token": "refresh-token"}]
    assert order == ["create_family", "build_access", "build_refresh", "apply_cookies"]


def test_admin_login_with_2fa_sets_partial_cookie(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partial_cookie_calls: list[str] = []
    cleared: list[tuple[str, ...]] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(
        ADMIN_RATE_LIMIT,
        "clear_failures",
        lambda *, settings, buckets: cleared.append(tuple(buckets)),
    )
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", lambda **kwargs: "partial-access")

    async def _unexpected_refresh_session(
        **kwargs,
    ) -> AUTH_REFRESH_SESSIONS.RefreshSessionIdentity:
        del kwargs
        raise AssertionError("partial login must not create a refresh family")

    monkeypatch.setattr(
        AUTH_REFRESH_SESSIONS,
        "create_refresh_session",
        _unexpected_refresh_session,
    )
    monkeypatch.setattr(
        AUTH_HELPERS,
        "set_partial_access_cookie",
        lambda **kwargs: partial_cookie_calls.append(kwargs["access_token"]),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": True}
    assert cleared == [login_buckets().keys]
    assert partial_cookie_calls == ["partial-access"]


def test_admin_verify_2fa_success_sets_full_auth_cookies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cookie_calls: list[dict[str, str]] = []
    cleared: list[tuple[str, ...]] = []
    order: list[str] = []

    async def _true_totp(**kwargs) -> bool:
        del kwargs
        return True

    async def _create_refresh_session(**kwargs) -> AUTH_REFRESH_SESSIONS.RefreshSessionIdentity:
        del kwargs
        order.append("create_family")
        return _refresh_session()

    def _build_access(**kwargs) -> str:
        del kwargs
        order.append("build_access")
        return "verified-access"

    def _build_refresh(**kwargs) -> str:
        assert kwargs["jti"] == _refresh_session().jti
        assert kwargs["family_id"] == _refresh_session().family_id
        order.append("build_refresh")
        return "verified-refresh"

    def _apply_cookies(**kwargs) -> None:
        order.append("apply_cookies")
        cookie_calls.append(
            {
                "access_token": kwargs["access_token"],
                "refresh_token": kwargs["refresh_token"],
            }
        )

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
        "clear_failures",
        lambda *, settings, buckets: cleared.append(tuple(buckets)),
    )
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _true_totp)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _create_refresh_session)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _build_access)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _build_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _apply_cookies)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 200
    assert response.json() == {
        "email": "admin@example.com",
        "role": "admin",
        "two_factor_verified": True,
    }
    assert cleared == [verify_buckets().keys]
    assert cookie_calls == [
        {"access_token": "verified-access", "refresh_token": "verified-refresh"}
    ]
    assert order == ["create_family", "build_access", "build_refresh", "apply_cookies"]


def test_admin_verify_2fa_skips_totp_check_when_2fa_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[bool] = []
    cookie_calls: list[dict[str, str]] = []
    cleared: list[tuple[str, ...]] = []

    async def _unexpected_totp(**kwargs) -> bool:
        del kwargs
        called.append(True)
        return False

    async def _create_refresh_session(**kwargs) -> AUTH_REFRESH_SESSIONS.RefreshSessionIdentity:
        del kwargs
        return _refresh_session()

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=False)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(
        AUTH_HELPERS, "verify_2fa_rate_limit_buckets", lambda **kwargs: verify_buckets()
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(
        ADMIN_RATE_LIMIT,
        "clear_failures",
        lambda *, settings, buckets: cleared.append(tuple(buckets)),
    )
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _unexpected_totp)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _create_refresh_session)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", lambda **kwargs: "verified-access")
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", lambda **kwargs: "verified-refresh")
    monkeypatch.setattr(
        ADMIN_AUTH,
        "apply_auth_cookies",
        lambda **kwargs: cookie_calls.append(
            {
                "access_token": kwargs["access_token"],
                "refresh_token": kwargs["refresh_token"],
            }
        ),
    )

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 200
    assert called == []
    assert cleared == [verify_buckets().keys]
    assert cookie_calls == [
        {"access_token": "verified-access", "refresh_token": "verified-refresh"}
    ]


def test_admin_login_returns_503_without_tokens_or_cookies_when_refresh_state_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _failed_create(**kwargs) -> AUTH_REFRESH_SESSIONS.RefreshSessionIdentity:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    def _unexpected_builder(**kwargs) -> str:
        del kwargs
        calls.append("builder")
        return "unexpected"

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=False)
    monkeypatch.setattr(AUTH_HELPERS, "login_rate_limit_buckets", lambda **kwargs: login_buckets())
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "clear_failures", lambda **kwargs: None)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _failed_create)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _unexpected_builder)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _unexpected_builder)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "apply_auth_cookies",
        lambda **kwargs: calls.append("cookies"),
    )

    response = client.post(
        "/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert calls == []
    assert "qa_admin_access" not in response.headers.get("set-cookie", "")
    assert "qa_admin_refresh" not in response.headers.get("set-cookie", "")


def test_admin_verify_2fa_returns_503_without_tokens_or_cookies_when_refresh_state_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _true_totp(**kwargs) -> bool:
        del kwargs
        return True

    async def _failed_create(**kwargs) -> AUTH_REFRESH_SESSIONS.RefreshSessionIdentity:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    def _unexpected_builder(**kwargs) -> str:
        del kwargs
        calls.append("builder")
        return "unexpected"

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(
        AUTH_HELPERS, "verify_2fa_rate_limit_buckets", lambda **kwargs: verify_buckets()
    )
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "clear_failures", lambda **kwargs: None)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _true_totp)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "create_refresh_session", _failed_create)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _unexpected_builder)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _unexpected_builder)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "apply_auth_cookies",
        lambda **kwargs: calls.append("cookies"),
    )

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert calls == []
    assert "qa_admin_access" not in response.headers.get("set-cookie", "")
    assert "qa_admin_refresh" not in response.headers.get("set-cookie", "")
