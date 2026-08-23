from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, Request, Response

from app.core.config import Settings
from app.services.admin.auth import ADMIN_ACCESS_COOKIE
from app.services.admin.auth_authority import ALLOWED_ADMIN_ROLES, normalize_admin_role
from app.services.internal_auth import extract_client_ip

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitBuckets:
    keys: tuple[str, ...]
    client_ip: str | None


def configured_admin_role(settings: Settings) -> str | None:
    resolved_role = normalize_admin_role(settings.admin_role)
    if resolved_role in ALLOWED_ADMIN_ROLES:
        return resolved_role
    return None


def _rate_limit_client_ip(*, request: Request, settings: Settings) -> str | None:
    return extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )


def _hashed_rate_limit_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        return "missing"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def login_rate_limit_buckets(
    *,
    request: Request,
    settings: Settings,
    email: str,
) -> RateLimitBuckets:
    client_ip = _rate_limit_client_ip(request=request, settings=settings)
    return RateLimitBuckets(
        keys=(
            f"admin_login:ip:{client_ip or 'unknown'}",
            f"admin_login:email:{_hashed_rate_limit_email(email)}",
        ),
        client_ip=client_ip,
    )


def verify_2fa_rate_limit_buckets(
    *,
    request: Request,
    settings: Settings,
    email: str,
) -> RateLimitBuckets:
    client_ip = _rate_limit_client_ip(request=request, settings=settings)
    return RateLimitBuckets(
        keys=(
            f"admin_2fa:ip:{client_ip or 'unknown'}",
            f"admin_2fa:email:{_hashed_rate_limit_email(email)}",
        ),
        client_ip=client_ip,
    )


def login_rate_limit_window_seconds(settings: Settings) -> int:
    return settings.admin_login_rate_limit_window_minutes * 60


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result


async def ensure_not_rate_limited(
    *,
    buckets: RateLimitBuckets,
    settings: Settings,
    is_rate_limited_fn,
    action: str,
) -> None:
    is_limited = await _maybe_await(
        is_rate_limited_fn(
            settings=settings,
            buckets=buckets.keys,
            limit=settings.admin_login_rate_limit_attempts,
            window_seconds=login_rate_limit_window_seconds(settings),
        )
    )
    if is_limited:
        logger.warning(
            "admin_auth_rate_limited",
            action=action,
            reason="rate_limited",
            client_ip=buckets.client_ip,
        )
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
    "RateLimitBuckets",
    "configured_admin_role",
    "ensure_allowed_admin_session",
    "ensure_not_rate_limited",
    "login_rate_limit_window_seconds",
    "login_rate_limit_buckets",
    "set_partial_access_cookie",
    "verify_2fa_rate_limit_buckets",
]
