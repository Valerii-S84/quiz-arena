from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth
from app.api.routes.admin import deps as admin_deps
from app.main import app


def _settings(*, two_fa_required: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        app_env="dev",
        admin_role="admin",
        admin_2fa_required=two_fa_required,
        admin_login_rate_limit_window_minutes=5,
        admin_login_rate_limit_attempts=3,
        admin_access_token_ttl_minutes=15,
        internal_api_trusted_proxies="127.0.0.1/32",
    )


def _principal(*, two_factor_verified: bool = False) -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=two_factor_verified,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_admin_login_rejects_invalid_credentials(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    failures: list[tuple[str, int]] = []
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=True)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(auth, "verify_login_credentials", lambda **kwargs: False)
    monkeypatch.setattr(auth, "record_failure", lambda *, bucket, window_seconds: failures.append((bucket, window_seconds)))

    response = client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_INVALID_CREDENTIALS"}}
    assert failures == [("bucket", 300)]


def test_admin_login_rejects_rate_limited_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=True)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: True)

    response = client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "E_RATE_LIMITED"}}


def test_admin_login_without_2fa_sets_full_auth_cookies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookie_calls: list[dict[str, str]] = []
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=False)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(auth, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(auth, "clear_failures", lambda **kwargs: None)
    monkeypatch.setattr(auth, "build_access_token", lambda **kwargs: "access-token")
    monkeypatch.setattr(auth, "build_refresh_token", lambda **kwargs: "refresh-token")
    monkeypatch.setattr(
        auth,
        "apply_auth_cookies",
        lambda **kwargs: cookie_calls.append(
            {
                "access_token": kwargs["access_token"],
                "refresh_token": kwargs["refresh_token"],
            }
        ),
    )

    response = client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": False}
    assert cookie_calls == [{"access_token": "access-token", "refresh_token": "refresh-token"}]


def test_admin_login_with_2fa_sets_partial_cookie(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial_cookie_calls: list[str] = []
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=True)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(auth, "verify_login_credentials", lambda **kwargs: True)
    monkeypatch.setattr(auth, "clear_failures", lambda **kwargs: None)
    monkeypatch.setattr(auth, "build_access_token", lambda **kwargs: "partial-access")
    monkeypatch.setattr(
        auth, "set_partial_access_cookie", lambda **kwargs: partial_cookie_calls.append(kwargs["access_token"])
    )

    response = client.post("/admin/auth/login", json={"email": "admin@example.com", "password": "secret123"})

    assert response.status_code == 200
    assert response.json() == {"requires_2fa": True}
    assert partial_cookie_calls == ["partial-access"]


def test_admin_verify_2fa_rejects_rate_limited_requests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: _principal(two_factor_verified=False)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: True)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "E_RATE_LIMITED"}}


def test_admin_verify_2fa_rejects_invalid_code(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    failures: list[tuple[str, int]] = []
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: _principal(two_factor_verified=False)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(auth, "record_failure", lambda *, bucket, window_seconds: failures.append((bucket, window_seconds)))
    monkeypatch.setattr(auth, "verify_totp_code", lambda **kwargs: auth.verify_totp_code.__class__(None))

    async def _false_totp(**kwargs) -> bool:
        del kwargs
        return False

    monkeypatch.setattr(auth, "verify_totp_code", _false_totp)

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_INVALID_TOTP"}}
    assert failures == [("bucket", 300)]


def test_admin_verify_2fa_success_sets_full_auth_cookies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookie_calls: list[dict[str, str]] = []

    async def _true_totp(**kwargs) -> bool:
        del kwargs
        return True

    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: _principal(two_factor_verified=False)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(auth, "clear_failures", lambda **kwargs: None)
    monkeypatch.setattr(auth, "verify_totp_code", _true_totp)
    monkeypatch.setattr(auth, "build_access_token", lambda **kwargs: "verified-access")
    monkeypatch.setattr(auth, "build_refresh_token", lambda **kwargs: "verified-refresh")
    monkeypatch.setattr(
        auth,
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
    assert cookie_calls == [{"access_token": "verified-access", "refresh_token": "verified-refresh"}]


def test_admin_verify_2fa_skips_totp_check_when_2fa_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[bool] = []
    cookie_calls: list[dict[str, str]] = []

    async def _unexpected_totp(**kwargs) -> bool:
        del kwargs
        called.append(True)
        return False

    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=False)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: _principal(two_factor_verified=False)
    monkeypatch.setattr(auth, "rate_limit_bucket", lambda **kwargs: "bucket")
    monkeypatch.setattr(auth, "is_rate_limited", lambda **kwargs: False)
    monkeypatch.setattr(auth, "clear_failures", lambda **kwargs: None)
    monkeypatch.setattr(auth, "verify_totp_code", _unexpected_totp)
    monkeypatch.setattr(auth, "build_access_token", lambda **kwargs: "verified-access")
    monkeypatch.setattr(auth, "build_refresh_token", lambda **kwargs: "verified-refresh")
    monkeypatch.setattr(
        auth,
        "apply_auth_cookies",
        lambda **kwargs: cookie_calls.append(
            {"access_token": kwargs["access_token"], "refresh_token": kwargs["refresh_token"]}
        ),
    )

    response = client.post("/admin/auth/2fa/verify", json={"code": "123456"})

    assert response.status_code == 200
    assert called == []
    assert cookie_calls == [{"access_token": "verified-access", "refresh_token": "verified-refresh"}]


def test_admin_auth_setup_refresh_logout_and_session(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_calls: list[bool] = []

    async def _setup(**kwargs) -> dict[str, str]:
        del kwargs
        return {"secret": "abc", "otpauth_url": "otpauth://x"}

    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: _principal(two_factor_verified=True)
    monkeypatch.setattr(auth, "get_totp_setup_payload", _setup)
    monkeypatch.setattr(auth, "decode_refresh_token", lambda **kwargs: _principal(two_factor_verified=True))
    monkeypatch.setattr(auth, "build_access_token", lambda **kwargs: "refresh-access")
    monkeypatch.setattr(auth, "build_refresh_token", lambda **kwargs: "refresh-refresh")
    monkeypatch.setattr(auth, "apply_auth_cookies", lambda **kwargs: None)
    monkeypatch.setattr(auth, "clear_auth_cookies", lambda response: clear_calls.append(True))

    setup = client.get("/admin/auth/2fa/setup")
    refresh = client.post("/admin/auth/refresh", cookies={"qa_admin_refresh": "refresh-cookie"})
    session = client.get("/admin/auth/session")
    logout = client.post("/admin/auth/logout")

    assert setup.status_code == 200
    assert setup.json() == {"secret": "abc", "otpauth_url": "otpauth://x"}
    assert refresh.status_code == 200
    assert refresh.json()["two_factor_verified"] is True
    assert session.status_code == 200
    assert session.json()["email"] == "admin@example.com"
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}
    assert clear_calls == [True]


@pytest.mark.parametrize(
    ("decoded_payload", "two_fa_required"),
    [
        (None, True),
        (_principal(two_factor_verified=True), True),
        (_principal(two_factor_verified=False), True),
    ],
)
def test_admin_refresh_rejects_invalid_or_unverified_tokens(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    decoded_payload,
    two_fa_required: bool,
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=two_fa_required)
    role_payload = decoded_payload
    if role_payload is not None and decoded_payload.two_factor_verified:
        role_payload = admin_deps.AdminPrincipal(
            id=decoded_payload.id,
            email=decoded_payload.email,
            role="viewer",
            two_factor_verified=decoded_payload.two_factor_verified,
            client_ip=decoded_payload.client_ip,
        )
    monkeypatch.setattr(auth, "decode_refresh_token", lambda **kwargs: role_payload)

    response = client.post("/admin/auth/refresh", cookies={"qa_admin_refresh": "refresh-cookie"})

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_UNAUTHORIZED"}}


@pytest.mark.parametrize(
    ("principal", "two_fa_required"),
    [
        (_principal(two_factor_verified=True), True),
        (_principal(two_factor_verified=False), True),
    ],
)
def test_admin_session_rejects_forbidden_principals(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    principal: admin_deps.AdminPrincipal,
    two_fa_required: bool,
) -> None:
    app.dependency_overrides[auth.get_settings] = lambda: _settings(two_fa_required=two_fa_required)
    if principal.two_factor_verified:
        principal = admin_deps.AdminPrincipal(
            id=principal.id,
            email=principal.email,
            role="viewer",
            two_factor_verified=True,
            client_ip=principal.client_ip,
        )
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal

    response = client.get("/admin/auth/session")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_UNAUTHORIZED"}}
