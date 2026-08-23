from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth, auth_session
from app.api.routes.admin import deps as admin_deps
from app.main import app
from app.services.admin import auth_authority
from app.services.admin.auth_common import AdminAuthStateError, AdminTokenPayload
from tests.api.admin.admin_auth_test_support import settings_stub

ADMIN_AUTH = auth_session.admin_auth
AUTH_REFRESH_SESSIONS = auth_session.auth_refresh_sessions


def _token_payload(
    *,
    token_type: str,
    two_factor_verified: bool = True,
) -> AdminTokenPayload:
    is_refresh = token_type == "refresh"
    return AdminTokenPayload(
        email="admin@example.com",
        role="admin",
        two_factor_verified=two_factor_verified,
        token_type=token_type,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        jti="refresh-jti-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" if is_refresh else None,
        family_id="refresh-family-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" if is_refresh else None,
    )


@pytest.mark.parametrize(
    ("path", "two_factor_verified"),
    [
        ("/admin/auth/2fa/setup", False),
        ("/admin/auth/session", True),
    ],
    ids=["pending", "access"],
)
def test_pending_and_access_authorization_deny_stale_database_identity(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    two_factor_verified: bool,
) -> None:
    async def _decode(**kwargs) -> AdminTokenPayload:
        del kwargs
        return _token_payload(
            token_type="access",
            two_factor_verified=two_factor_verified,
        )

    async def _resolve(**kwargs):
        assert kwargs == {
            "email": "admin@example.com",
            "expected_role": "admin",
        }
        return None

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(admin_deps, "decode_access_token", _decode)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _resolve)

    client.cookies.set("qa_admin_access", "access-cookie")
    response = client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_UNAUTHORIZED"}}


@pytest.mark.parametrize(
    ("path", "two_factor_verified"),
    [
        ("/admin/auth/2fa/setup", False),
        ("/admin/auth/session", True),
    ],
    ids=["pending", "access"],
)
def test_pending_and_access_authority_outage_returns_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    two_factor_verified: bool,
) -> None:
    async def _decode(**kwargs) -> AdminTokenPayload:
        del kwargs
        return _token_payload(
            token_type="access",
            two_factor_verified=two_factor_verified,
        )

    async def _outage(**kwargs):
        del kwargs
        raise AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(admin_deps, "decode_access_token", _decode)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _outage)

    client.cookies.set("qa_admin_access", "access-cookie")
    response = client.get(path)

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}


def test_refresh_denies_stale_authority_before_rotation_or_issuance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _decode(**kwargs) -> AdminTokenPayload:
        del kwargs
        return _token_payload(token_type="refresh")

    async def _deny(**kwargs):
        del kwargs
        return None

    async def _unexpected_rotation(**kwargs):
        del kwargs
        calls.append("rotation")
        return None

    def _unexpected_issuer(**kwargs) -> str:
        del kwargs
        calls.append("issuer")
        return "unexpected"

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _deny)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "rotate_refresh_session", _unexpected_rotation)
    monkeypatch.setattr(ADMIN_AUTH, "build_access_token", _unexpected_issuer)
    monkeypatch.setattr(ADMIN_AUTH, "build_refresh_token", _unexpected_issuer)
    monkeypatch.setattr(ADMIN_AUTH, "apply_auth_cookies", _unexpected_issuer)

    client.cookies.set("qa_admin_refresh", "refresh-cookie")
    response = client.post("/admin/auth/refresh")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "E_UNAUTHORIZED"}}
    assert calls == []
    assert "set-cookie" not in response.headers


def test_refresh_authority_outage_returns_503_before_rotation_or_issuance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _decode(**kwargs) -> AdminTokenPayload:
        del kwargs
        return _token_payload(token_type="refresh")

    async def _outage(**kwargs):
        del kwargs
        raise AdminAuthStateError("down")

    async def _unexpected_rotation(**kwargs):
        del kwargs
        calls.append("rotation")
        return None

    app.dependency_overrides[auth.get_settings] = lambda: settings_stub(two_fa_required=True)
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode)
    monkeypatch.setattr(auth_authority, "resolve_current_admin_authority", _outage)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "rotate_refresh_session", _unexpected_rotation)
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_access_token",
        lambda **kwargs: calls.append("access"),
    )
    monkeypatch.setattr(
        ADMIN_AUTH,
        "build_refresh_token",
        lambda **kwargs: calls.append("refresh"),
    )
    monkeypatch.setattr(
        ADMIN_AUTH,
        "apply_auth_cookies",
        lambda **kwargs: calls.append("cookies"),
    )

    client.cookies.set("qa_admin_refresh", "refresh-cookie")
    response = client.post("/admin/auth/refresh")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert calls == []
    assert "set-cookie" not in response.headers
