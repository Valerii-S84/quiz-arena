from __future__ import annotations

import pytest

from tests.services.admin_auth_test_support import (
    CookieResponse,
    admin_auth,
    reset_admin_auth_redis_client,
    settings_stub,
)


@pytest.fixture(autouse=True)
def _reset_redis_client() -> None:
    reset_admin_auth_redis_client()


def test_get_password_hash_rejects_missing_configuration() -> None:
    settings = settings_stub(admin_password_hash="", admin_password_plain=" ")

    with pytest.raises(admin_auth.AdminAuthError):
        admin_auth._get_password_hash(settings)


def test_get_password_hash_builds_fallback_hash_from_plain_password() -> None:
    password_hash = admin_auth._get_password_hash(
        settings_stub(admin_password_hash="", admin_password_plain="secret123")
    )

    assert admin_auth._pwd_context.verify("secret123", password_hash) is True


def test_verify_login_credentials_requires_matching_email_and_password() -> None:
    password_hash = admin_auth._pwd_context.hash("secret123")
    settings = settings_stub(admin_password_hash=password_hash, admin_password_plain="")

    assert (
        admin_auth.verify_login_credentials(
            settings=settings,
            email="ADMIN@example.com",
            password="secret123",
        )
        is True
    )
    assert (
        admin_auth.verify_login_credentials(
            settings=settings,
            email="viewer@example.com",
            password="secret123",
        )
        is False
    )
    assert (
        admin_auth.verify_login_credentials(
            settings=settings,
            email="admin@example.com",
            password="wrong",
        )
        is False
    )


def test_auth_cookie_helpers_set_and_clear_expected_cookies() -> None:
    response = CookieResponse()
    settings = settings_stub(
        app_env="prod",
        admin_access_token_ttl_minutes=0,
        admin_refresh_token_ttl_days=0,
    )

    admin_auth.apply_auth_cookies(
        settings=settings,
        response=response,
        access_token="access-token",
        refresh_token="refresh-token",
    )
    admin_auth.clear_auth_cookies(response)

    assert response.set_calls == [
        {
            "key": admin_auth.ADMIN_ACCESS_COOKIE,
            "value": "access-token",
            "max_age": 60,
            "httponly": True,
            "samesite": "strict",
            "secure": True,
            "path": "/",
        },
        {
            "key": admin_auth.ADMIN_REFRESH_COOKIE,
            "value": "refresh-token",
            "max_age": 60,
            "httponly": True,
            "samesite": "strict",
            "secure": True,
            "path": "/",
        },
    ]
    assert response.delete_calls == [
        {"key": admin_auth.ADMIN_ACCESS_COOKIE, "path": "/"},
        {"key": admin_auth.ADMIN_REFRESH_COOKIE, "path": "/"},
    ]
