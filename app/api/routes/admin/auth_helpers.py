from __future__ import annotations

from fastapi import HTTPException, Request, Response

from app.api.routes.admin.deps import ALLOWED_ADMIN_ROLES, normalize_admin_role
from app.core.config import Settings
from app.services.admin.auth import ADMIN_ACCESS_COOKIE
from app.services.internal_auth import extract_client_ip


def configured_admin_role(settings: Settings) -> str:
    resolved_role = normalize_admin_role(settings.admin_role)
    if resolved_role in ALLOWED_ADMIN_ROLES:
        return resolved_role
    return "admin"


def rate_limit_bucket(*, request: Request, settings: Settings) -> str:
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )
    return client_ip or "unknown"


def login_rate_limit_window_seconds(settings: Settings) -> int:
    return settings.admin_login_rate_limit_window_minutes * 60


def ensure_not_rate_limited(
    *,
    bucket: str,
    settings: Settings,
    is_rate_limited_fn,
) -> None:
    if is_rate_limited_fn(
        bucket=bucket,
        limit=settings.admin_login_rate_limit_attempts,
        window_seconds=login_rate_limit_window_seconds(settings),
    ):
        raise HTTPException(status_code=429, detail={"code": "E_RATE_LIMITED"})


def ensure_allowed_admin_session(
    *,
    role: str,
    two_factor_verified: bool,
    settings: Settings,
) -> None:
    if normalize_admin_role(role) not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    if settings.admin_2fa_required and not two_factor_verified:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})


def set_partial_access_cookie(*, settings: Settings, response: Response, access_token: str) -> None:
    secure = settings.app_env != "dev"
    ttl_seconds = max(60, settings.admin_access_token_ttl_minutes * 60)
    response.set_cookie(
        key=ADMIN_ACCESS_COOKIE,
        value=access_token,
        max_age=ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


__all__ = [
    "configured_admin_role",
    "ensure_allowed_admin_session",
    "ensure_not_rate_limited",
    "login_rate_limit_window_seconds",
    "rate_limit_bucket",
    "set_partial_access_cookie",
]
