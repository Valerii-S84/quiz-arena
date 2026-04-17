from __future__ import annotations

import structlog
from fastapi import Request

from app.core.config import Settings
from app.services.admin import auth as admin_auth
from app.services.admin import rate_limit as admin_rate_limit

from . import auth_helpers, auth_responses

logger = structlog.get_logger(__name__)


def _raise_auth_state_unavailable(
    *,
    action: str,
    client_ip: str | None,
    exc: admin_auth.AdminAuthStateError,
) -> None:
    logger.warning(
        "admin_auth_rate_limit_state_unavailable",
        action=action,
        reason="rate_limit_state_unavailable",
        client_ip=client_ip,
    )
    raise auth_responses.auth_state_unavailable_http_error() from exc


async def _ensure_allowed(
    *,
    buckets: auth_helpers.RateLimitBuckets,
    settings: Settings,
    action: str,
) -> auth_helpers.RateLimitBuckets:
    try:
        await auth_helpers.ensure_not_rate_limited(
            buckets=buckets,
            settings=settings,
            is_rate_limited_fn=admin_rate_limit.is_rate_limited,
            action=action,
        )
    except admin_auth.AdminAuthStateError as exc:
        _raise_auth_state_unavailable(action=action, client_ip=buckets.client_ip, exc=exc)
    return buckets


async def ensure_login_allowed(
    *,
    request: Request,
    settings: Settings,
    email: str,
) -> auth_helpers.RateLimitBuckets:
    return await _ensure_allowed(
        buckets=auth_helpers.login_rate_limit_buckets(
            request=request,
            settings=settings,
            email=email,
        ),
        settings=settings,
        action="login",
    )


async def ensure_verify_2fa_allowed(
    *,
    request: Request,
    settings: Settings,
    email: str,
) -> auth_helpers.RateLimitBuckets:
    return await _ensure_allowed(
        buckets=auth_helpers.verify_2fa_rate_limit_buckets(
            request=request,
            settings=settings,
            email=email,
        ),
        settings=settings,
        action="verify_2fa",
    )


async def record_failure(
    *,
    settings: Settings,
    buckets: auth_helpers.RateLimitBuckets,
    window_seconds: int,
    action: str,
) -> None:
    try:
        await auth_helpers._maybe_await(
            admin_rate_limit.record_failure(
                settings=settings,
                buckets=buckets.keys,
                window_seconds=window_seconds,
            )
        )
    except admin_auth.AdminAuthStateError as exc:
        _raise_auth_state_unavailable(action=action, client_ip=buckets.client_ip, exc=exc)


async def clear_failures(
    *,
    settings: Settings,
    buckets: auth_helpers.RateLimitBuckets,
    action: str,
) -> None:
    try:
        await auth_helpers._maybe_await(
            admin_rate_limit.clear_failures(settings=settings, buckets=buckets.keys)
        )
    except admin_auth.AdminAuthStateError as exc:
        _raise_auth_state_unavailable(action=action, client_ip=buckets.client_ip, exc=exc)


__all__ = [
    "clear_failures",
    "ensure_login_allowed",
    "ensure_verify_2fa_allowed",
    "record_failure",
]
