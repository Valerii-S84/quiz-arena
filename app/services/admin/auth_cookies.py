from __future__ import annotations

from app.core.config import Settings

from .auth_common import ADMIN_ACCESS_COOKIE, ADMIN_REFRESH_COOKIE


def apply_auth_cookies(
    *, settings: Settings, response, access_token: str, refresh_token: str
) -> None:
    secure = settings.app_env != "dev"
    response.set_cookie(
        key=ADMIN_ACCESS_COOKIE,
        value=access_token,
        max_age=max(60, settings.admin_access_token_ttl_minutes * 60),
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        key=ADMIN_REFRESH_COOKIE,
        value=refresh_token,
        max_age=max(60, settings.admin_refresh_token_ttl_days * 24 * 3600),
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(key=ADMIN_ACCESS_COOKIE, path="/")
    response.delete_cookie(key=ADMIN_REFRESH_COOKIE, path="/")
