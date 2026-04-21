from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth
from app.api.routes.admin import deps as admin_deps
from app.main import app
from tests.api.admin.admin_auth_test_support import principal_stub, settings_stub

ADMIN_AUTH = auth.admin_auth
ADMIN_RATE_LIMIT = auth.admin_rate_limit
AUTH_HELPERS = auth.auth_helpers


async def _rate_limit_false(**kwargs) -> bool:
    del kwargs
    return False


async def _rate_limit_true(**kwargs) -> bool:
    del kwargs
    return True


async def _rate_limit_noop(**kwargs) -> None:
    del kwargs


def test_admin_login_rejects_invalid_credentials(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    failures: list[tuple[str, int]] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: False)

    async def _record_failure(**kwargs) -> None:
        failures.append((kwargs["bucket"], kwargs["window_seconds"]))

    monkeypatch.setattr(ADMIN_RATE_LIMIT, "record_failure", _record_failure)

    response = client.post(
        "/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_INVALID_CREDENTIALS"}}
    assert failures == [("bucket", 300)]


def test_admin_login_rejects_rate_limited_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_true)

    response = client.post(
        "/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    )

    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "E_RATE_LIMITED"}}


def test_admin_login_without_2fa_sets_full_auth_cookies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookie_calls: list[dict[str, str]] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=False)
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "clear_failures", _rate_limit_noop)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", lambda **kwargs: "access-token")
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", lambda **kwargs: "refresh-token")
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

    response = client.post(
        "/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    )

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": False}
    assert cookie_calls == [{"access_token": "access-token", "refresh_token": "refresh-token"}]


def test_admin_login_with_2fa_sets_partial_cookie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial_cookie_calls: list[str] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "clear_failures", _rate_limit_noop)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", lambda **kwargs: "partial-access")
    monkeypatch.setattr(
        AUTH_HELPERS,
        "set_partial_access_cookie",
        lambda **kwargs: partial_cookie_calls.append(kwargs["access_token"]),
    )

    response = client.post(
        "/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    )

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": True}
    assert partial_cookie_calls == ["partial-access"]


def test_admin_verify_2fa_rejects_rate_limited_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_true)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "E_RATE_LIMITED"}}


def test_admin_verify_2fa_rejects_invalid_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    failures: list[tuple[str, int]] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)

    async def _record_failure(**kwargs) -> None:
        failures.append((kwargs["bucket"], kwargs["window_seconds"]))

    monkeypatch.setattr(ADMIN_RATE_LIMIT, "record_failure", _record_failure)

    async def _false_totp(**kwargs) -> bool:
        del kwargs
        return False

    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _false_totp)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_INVALID_TOTP"}}
    assert failures == [("bucket", 300)]


def test_admin_verify_2fa_returns_503_when_auth_state_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _error_totp(**kwargs) -> bool:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _error_totp)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_verify_2fa_success_sets_full_auth_cookies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookie_calls: list[dict[str, str]] = []

    async def _true_totp(**kwargs) -> bool:
        del kwargs
        return True

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "clear_failures", _rate_limit_noop)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _true_totp)
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
    assert response.json() == {
        "email": "admin@example.com",
        "role": "admin",
        "two_factor_verified": True,
    }
    assert cookie_calls == [
        {"access_token": "verified-access", "refresh_token": "verified-refresh"}
    ]


def test_admin_verify_2fa_skips_totp_check_when_2fa_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[bool] = []
    cookie_calls: list[dict[str, str]] = []

    async def _unexpected_totp(**kwargs) -> bool:
        del kwargs
        called.append(True)
        return False

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=False)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "clear_failures", _rate_limit_noop)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _unexpected_totp)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", lambda **kwargs: "verified-access")
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", lambda **kwargs: "verified-refresh")
    monkeypatch.setattr(
        ADMIN_AUTH,
        "apply_auth_cookies",
        lambda **kwargs: cookie_calls.append(
            {"access_token": kwargs["access_token"], "refresh_token": kwargs["refresh_token"]}
        ),
    )

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 200
    assert called == []
    assert cookie_calls == [
        {"access_token": "verified-access", "refresh_token": "verified-refresh"}
    ]


def test_admin_login_returns_503_when_rate_limit_state_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _state_down(**kwargs) -> bool:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _state_down)

    response = client.post(
        "/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_login_returns_503_when_failure_cannot_be_recorded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _state_down(**kwargs) -> None:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_AUTH, "verify_login_credentials", lambda **kwargs: False)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "record_failure", _state_down)

    response = client.post(
        "/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_verify_2fa_returns_503_when_failure_cannot_be_recorded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _false_totp(**kwargs) -> bool:
        del kwargs
        return False

    async def _state_down(**kwargs) -> None:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(AUTH_HELPERS, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "is_rate_limited", _rate_limit_false)
    monkeypatch.setattr(ADMIN_AUTH, "verify_totp_code", _false_totp)
    monkeypatch.setattr(ADMIN_RATE_LIMIT, "record_failure", _state_down)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
