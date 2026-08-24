from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import auth
from app.api.routes.admin import auth_session as auth_session_routes
from app.main import app
from app.services.admin import auth_tokens
from tests.api.admin.admin_auth_test_support import settings_stub

ADMIN_AUTH = auth.admin_auth
AUTH_REFRESH_SESSIONS = auth_session_routes.auth_refresh_sessions
ACCESS_REVOCATION = auth_tokens.AccessTokenRevocation(
    key="qa_admin:revoked_token:access-hash",
    ttl_seconds=300,
)


def _assert_auth_cookie_deletions(response) -> None:
    set_cookie_headers = response.headers.get_list("set-cookie")
    for cookie_name in ("qa_admin_access", "qa_admin_refresh"):
        assert any(
            header.startswith(f'{cookie_name}=""') and "Max-Age=0" in header
            for header in set_cookie_headers
        )


def _refresh_payload() -> SimpleNamespace:
    return SimpleNamespace(family_id="family-current")


@pytest.mark.parametrize(
    (
        "access_cookie",
        "refresh_cookie",
        "expects_access",
        "expected_family_id",
    ),
    [
        ("valid-access", None, True, None),
        (None, "valid-refresh", False, "family-current"),
        ("valid-access", "valid-refresh", True, "family-current"),
        (None, None, False, None),
        ("malformed-access", "valid-refresh", False, "family-current"),
        ("valid-access", "malformed-refresh", True, None),
    ],
)
def test_logout_revokes_every_valid_identity_before_clearing_cookies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    access_cookie: str | None,
    refresh_cookie: str | None,
    expects_access: bool,
    expected_family_id: str | None,
) -> None:
    revoke_calls: list[dict[str, object]] = []

    def _resolve_access(*, token: str, **kwargs):
        del kwargs
        return ACCESS_REVOCATION if token == "valid-access" else None

    async def _decode_refresh(*, token: str, **kwargs):
        del kwargs
        return _refresh_payload() if token == "valid-refresh" else None

    async def _revoke_logout(**kwargs) -> None:
        revoke_calls.append(kwargs)

    app.dependency_overrides[auth.get_settings] = settings_stub
    monkeypatch.setattr(
        auth_session_routes.auth_tokens, "resolve_access_token_revocation", _resolve_access
    )
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode_refresh)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "revoke_logout_session", _revoke_logout)
    if access_cookie is not None:
        client.cookies.set("qa_admin_access", access_cookie)
    if refresh_cookie is not None:
        client.cookies.set("qa_admin_refresh", refresh_cookie)

    response = client.post("/admin/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(revoke_calls) == 1
    assert revoke_calls[0]["access_revocation"] == (ACCESS_REVOCATION if expects_access else None)
    assert revoke_calls[0]["refresh_family_id"] == expected_family_id
    _assert_auth_cookie_deletions(response)


def test_logout_redis_failure_retains_cookies_and_retry_clears_them(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def _resolve_access(**kwargs):
        del kwargs
        return ACCESS_REVOCATION

    async def _decode_refresh(**kwargs):
        del kwargs
        return _refresh_payload()

    async def _revoke_logout(**kwargs) -> None:
        nonlocal attempts
        del kwargs
        attempts += 1
        if attempts == 1:
            raise ADMIN_AUTH.AdminAuthStateError("down")

    app.dependency_overrides[auth.get_settings] = settings_stub
    monkeypatch.setattr(
        auth_session_routes.auth_tokens, "resolve_access_token_revocation", _resolve_access
    )
    monkeypatch.setattr(ADMIN_AUTH, "decode_refresh_token", _decode_refresh)
    monkeypatch.setattr(AUTH_REFRESH_SESSIONS, "revoke_logout_session", _revoke_logout)
    client.cookies.set("qa_admin_access", "valid-access")
    client.cookies.set("qa_admin_refresh", "valid-refresh")

    failed_response = client.post("/admin/auth/logout")

    assert failed_response.status_code == 503
    assert failed_response.json() == {"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}}
    assert "set-cookie" not in failed_response.headers
    assert client.cookies.get("qa_admin_access") == "valid-access"
    assert client.cookies.get("qa_admin_refresh") == "valid-refresh"

    recovered_response = client.post("/admin/auth/logout")

    assert recovered_response.status_code == 200
    assert recovered_response.json() == {"ok": True}
    assert attempts == 2
    _assert_auth_cookie_deletions(recovered_response)
