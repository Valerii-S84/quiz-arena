from __future__ import annotations

from fastapi import Request, Response

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
