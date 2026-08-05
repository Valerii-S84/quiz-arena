from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth
from app.api.routes.admin import auth_session as auth_session_routes
from app.api.routes.admin import deps as admin_deps
from app.main import app
from tests.api.admin.admin_auth_test_support import principal_stub, settings_stub

ADMIN_AUTH = auth.admin_auth
AUTH_REFRESH_SESSIONS = auth_session_routes.auth_refresh_sessions


def _refresh_payload_stub(
    *, role: str = "admin", two_factor_verified: bool = True
) -> SimpleNamespace:
    return SimpleNamespace(
        email="admin@example.com",
        role=role,
        two_factor_verified=two_factor_verified,
        family_id="refresh-family-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        jti="refresh-jti-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )


def _successful_rotation() -> AUTH_REFRESH_SESSIONS.RefreshRotationResult:
    return AUTH_REFRESH_SESSIONS.RefreshRotationResult(
        status=AUTH_REFRESH_SESSIONS.RefreshRotationStatus.ROTATED,
        session=AUTH_REFRESH_SESSIONS.RefreshSessionIdentity(
            family_id="refresh-family-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            jti="successor-jti-cccccccccccccccccccccccccccccccc",
        ),
    )


def test_admin_auth_setup_refresh_logout_and_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_calls: list[bool] = []
    revoked_state: list[tuple[str, str]] = []

    async def _setup(**kwargs) -> dict[str, str]:
        del kwargs
        return {"secret": "abc", "otpauth_url": "otpauth://x"}

    async def _decoded_refresh(**kwargs):
        del kwargs
        return _refresh_payload_stub()

    async def _rotate_refresh(**kwargs):
        del kwargs
        return _successful_rotation()

    async def _revoke_access(**kwargs) -> None:
        revoked_state.append(("access", kwargs["token"]))

    async def _revoke_family(**kwargs) -> None:
        revoked_state.append(("family", kwargs["family_id"]))

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=True
    )
    monkeypatch.setattr(ADMIN_AUTH, "get_totp_setup_payload", _setup)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decoded_refresh)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "rotate_refresh_session", _rotate_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", lambda **kwargs: "refresh-access")
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", lambda **kwargs: "refresh-refresh")
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", lambda **kwargs: None)
    monkeypatch.setattr(ADMIN_AUTH, "clear_auth_cookies", lambda response: clear_calls.append(True))
    monkeypatch.setattr(ADMIN_AUTH, "revoke_access_token", _revoke_access)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "revoke_refresh_family", _revoke_family)

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
    assert revoked_state == [
        ("access", "access-cookie"),
        ("family", _refresh_payload_stub().family_id),
    ]


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


def test_admin_auth_setup_denies_existing_totp_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _setup(**kwargs) -> None:
        del kwargs
        return None

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    app.dependency_overrides[admin_deps.get_pending_admin] = lambda: principal_stub(
        two_factor_verified=False
    )
    monkeypatch.setattr(ADMIN_AUTH, "get_totp_setup_payload", _setup)

    response = client.get("/admin/auth/2fa/setup")

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "E_FORBIDDEN"}}


@pytest.mark.parametrize(
    "path",
    [
        "/admin/auth/2fa/reset",
        "/admin/auth/2fa/recover",
        "/admin/auth/2fa/rotate",
    ],
)
def test_admin_auth_has_no_password_only_totp_recovery_path(client: TestClient, path: str) -> None:
    response = client.post(path)

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("decoded_payload", "two_fa_required"),
    [
        (None, True),
        (_refresh_payload_stub(role="viewer"), True),
        (_refresh_payload_stub(two_factor_verified=False), True),
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
        return decoded_payload

    async def _unexpected_rotate(**kwargs):
        del kwargs
        raise AssertionError("invalid refresh claims must be rejected before rotation")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(
        two_fa_required=two_fa_required
    )
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode_refresh)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "rotate_refresh_session", _unexpected_rotate)

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


def test_admin_refresh_returns_503_without_replacing_cookies_when_rotation_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def _decode_refresh(**kwargs):
        del kwargs
        return _refresh_payload_stub()

    async def _failed_rotation(**kwargs):
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    def _unexpected_builder(**kwargs) -> str:
        del kwargs
        calls.append("builder")
        return "unexpected"

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode_refresh)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "rotate_refresh_session", _failed_rotation)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _unexpected_builder)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _unexpected_builder)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "apply_auth_cookies",
        lambda **kwargs: calls.append("cookies"),
    )

    client.cookies.set("qa_admin_refresh", "predecessor-token")
    response = client.post("/admin/auth/refresh")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert calls == []
    assert "set-cookie" not in response.headers


def test_admin_refresh_rotates_before_replacing_both_cookies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    original_apply_cookies = ADMIN_AUTH.apply_auth_cookies
    successor = _successful_rotation()

    async def _decode_refresh(**kwargs):
        del kwargs
        return _refresh_payload_stub()

    async def _rotate_refresh(**kwargs):
        del kwargs
        order.append("rotate")
        return successor

    def _build_access(**kwargs) -> str:
        del kwargs
        order.append("build_access")
        return "new-access-token"

    def _build_refresh(**kwargs) -> str:
        assert successor.session is not None
        assert kwargs["jti"] == successor.session.jti
        assert kwargs["family_id"] == successor.session.family_id
        order.append("build_refresh")
        return "new-refresh-token"

    def _apply_cookies(**kwargs) -> None:
        order.append("apply_cookies")
        original_apply_cookies(**kwargs)

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode_refresh)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "rotate_refresh_session", _rotate_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _build_access)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _build_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _apply_cookies)

    client.cookies.set("qa_admin_access", "old-access-token")
    client.cookies.set("qa_admin_refresh", "predecessor-token")
    response = client.post("/admin/auth/refresh")

    assert response.status_code == 200
    assert response.cookies.get("qa_admin_access") == "new-access-token"
    assert response.cookies.get("qa_admin_refresh") == "new-refresh-token"
    assert order == ["rotate", "build_access", "build_refresh", "apply_cookies"]


def test_admin_logout_returns_503_when_access_revocation_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _revoke_access(**kwargs) -> None:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    async def _revoke_family(**kwargs) -> None:
        del kwargs
        raise AssertionError("family revocation should not run after access failure")

    clear_calls: list[bool] = []

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "revoke_access_token", _revoke_access)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "revoke_refresh_family", _revoke_family)
    monkeypatch.setattr(ADMIN_AUTH, "clear_auth_cookies", lambda response: clear_calls.append(True))

    client.cookies.set("qa_admin_access", "access-cookie")
    response = client.post("/admin/auth/logout")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert clear_calls == [True]


def test_admin_logout_returns_503_when_family_revocation_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _decoded_refresh(**kwargs):
        del kwargs
        return _refresh_payload_stub()

    async def _revoke_access(**kwargs) -> None:
        del kwargs

    async def _revoke_family(**kwargs) -> None:
        del kwargs
        raise ADMIN_AUTH.AdminAuthStateError("down")

    clear_calls: list[bool] = []
    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decoded_refresh)
    monkeypatch.setattr(ADMIN_AUTH, "revoke_access_token", _revoke_access)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "revoke_refresh_family", _revoke_family)
    monkeypatch.setattr(ADMIN_AUTH, "clear_auth_cookies", lambda response: clear_calls.append(True))

    client.cookies.set("qa_admin_refresh", "refresh-cookie")
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
