from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth
from app.api.routes.admin import deps as admin_deps
from app.main import app
from tests.api.admin.admin_auth_test_support import principal_stub, settings_stub

ADMIN_AUTH = auth.admin_auth


def test_admin_auth_setup_refresh_logout_and_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_calls: list[bool] = []
    revoked_tokens: list[tuple[str, str]] = []

    async def _setup(**kwargs) -> dict[str, str]:
        del kwargs
        return {"secret": "abc", "otpauth_url": "otpauth://x"}

    async def _decoded_refresh(**kwargs):
        del kwargs
        return principal_stub(two_factor_verified=True)

    async def _revoke_access(**kwargs) -> None:
        revoked_tokens.append(("access", kwargs["token"]))

    async def _revoke_refresh(**kwargs) -> None:
        revoked_tokens.append(("refresh", kwargs["token"]))

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=True
    )
    monkeypatch.setattr(ADMIN_AUTH, "get_totp_setup_payload", _setup)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decoded_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", lambda **kwargs: "refresh-access")
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", lambda **kwargs: "refresh-refresh")
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", lambda **kwargs: None)
    monkeypatch.setattr(ADMIN_AUTH, "clear_auth_cookies", lambda response: clear_calls.append(True))
    monkeypatch.setattr(ADMIN_AUTH, "revoke_access_token", _revoke_access)
    monkeypatch.setattr(ADMIN_AUTH, "revoke_refresh_token", _revoke_refresh)

    setup = client.get("/admin/auth/2fa/setup")
    client.cookies.set("qa_admin_access", "access-cookie")
    client.cookies.set("qa_admin_refresh", "refresh-cookie")
    refresh = client.post("/admin/auth/refresh")
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
    assert revoked_tokens == [("access", "access-cookie"), ("refresh", "refresh-cookie")]


def test_admin_auth_setup_returns_503_when_auth_state_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _setup(**kwargs) -> dict[str, str]:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=True
    )
    monkeypatch.setattr(ADMIN_AUTH, "get_totp_setup_payload", _setup)

    response = client.get("/admin/auth/2fa/setup")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


@pytest.mark.parametrize(
    ("decoded_payload", "two_fa_required"),
    [
        (None, True),
        (principal_stub(two_factor_verified=True), True),
        (principal_stub(two_factor_verified=False), True),
    ],
)
def test_admin_refresh_rejects_invalid_or_unverified_tokens(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    decoded_payload,
    two_fa_required: bool,
) -> None:
    async def _decode_refresh(**kwargs):
        del kwargs
        return role_payload

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(
        two_fa_required=two_fa_required
    )
    role_payload = decoded_payload
    if role_payload is not None and decoded_payload.two_factor_verified:
        role_payload = admin_deps.AdminPrincipal(
            id=decoded_payload.id,
            email=decoded_payload.email,
            role="viewer",
            two_factor_verified=decoded_payload.two_factor_verified,
            client_ip=decoded_payload.client_ip,
        )
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode_refresh)

    client.cookies.set("qa_admin_refresh", "refresh-cookie")
    response = client.post("/admin/auth/refresh")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_UNAUTHORIZED"}}


def test_admin_refresh_returns_503_when_auth_state_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _decode_refresh(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode_refresh)

    client.cookies.set("qa_admin_refresh", "refresh-cookie")
    response = client.post("/admin/auth/refresh")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_admin_logout_returns_503_when_revocation_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _revoke_access(**kwargs) -> None:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    async def _revoke_refresh(**kwargs) -> None:
        del kwargs
        raise AssertionError("refresh revocation should not run after access failure")

    clear_calls: list[bool] = []

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "revoke_access_token", _revoke_access)
    monkeypatch.setattr(ADMIN_AUTH, "revoke_refresh_token", _revoke_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "clear_auth_cookies", lambda response: clear_calls.append(True))

    client.cookies.set("qa_admin_access", "access-cookie")
    response = client.post("/admin/auth/logout")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert clear_calls == [True]


@pytest.mark.parametrize(
    ("principal", "two_fa_required"),
    [
        (principal_stub(two_factor_verified=True), True),
        (principal_stub(two_factor_verified=False), True),
    ],
)
def test_admin_session_rejects_forbidden_principals(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    principal: admin_deps.AdminPrincipal,
    two_fa_required: bool,
) -> None:
    del monkeypatch
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(
        two_fa_required=two_fa_required
    )
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


def test_admin_session_returns_503_when_auth_state_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _decode_access(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(admin_deps, "decode_access_token", _decode_access)

    client.cookies.set("qa_admin_access", "access-cookie")
    response = client.get("/admin/auth/session")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
