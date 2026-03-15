from __future__ import annotations

import sys
from collections import deque
from time import monotonic
from types import ModuleType
from typing import cast
from urllib.parse import urlsplit

import structlog
from fastapi import HTTPException, Request

from app.services.internal_auth import (
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_request_authenticated,
)

logger = structlog.get_logger(__name__)


def _ops_ui_module() -> ModuleType:
    return cast(ModuleType, sys.modules[__package__])


def _assert_internal_ip_access(request: Request) -> str | None:
    settings = _ops_ui_module().get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )
    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("ops_ui_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    return client_ip


def _normalized_origin(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _assert_same_origin_form_post(request: Request, *, client_ip: str | None) -> None:
    module = _ops_ui_module()
    content_type = (
        (request.headers.get("content-type") or "").split(";", maxsplit=1)[0].strip().lower()
    )
    if content_type != module.OPS_UI_FORM_CONTENT_TYPE:
        logger.warning(
            "ops_ui_auth_failed",
            reason="invalid_form_content_type",
            client_ip=client_ip,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    host = (request.headers.get("host") or "").strip().lower()
    if not host:
        logger.warning("ops_ui_auth_failed", reason="missing_host_header", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    allowed_origins = {f"http://{host}", f"https://{host}"}

    origin = _normalized_origin(request.headers.get("origin"))
    if origin is not None:
        if origin in allowed_origins:
            return
        logger.warning(
            "ops_ui_auth_failed",
            reason="origin_mismatch",
            client_ip=client_ip,
            origin=origin,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    referer = _normalized_origin(request.headers.get("referer"))
    if referer not in allowed_origins:
        logger.warning(
            "ops_ui_auth_failed",
            reason="referer_mismatch",
            client_ip=client_ip,
            referer=referer,
        )
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


def _login_bucket_key(client_ip: str | None) -> str:
    return client_ip or "unknown"


def _prune_login_failures(attempts: deque[float], *, now: float) -> None:
    cutoff = now - _ops_ui_module().OPS_UI_LOGIN_FAILED_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()


def _is_login_rate_limited(client_ip: str | None) -> bool:
    module = _ops_ui_module()
    key = _login_bucket_key(client_ip)
    now = monotonic()
    with module._LOGIN_THROTTLE_LOCK:
        attempts = module._LOGIN_FAILED_ATTEMPTS.get(key)
        if attempts is None:
            return False
        _prune_login_failures(attempts, now=now)
        if not attempts:
            module._LOGIN_FAILED_ATTEMPTS.pop(key, None)
            return False
        return len(attempts) >= module.OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS


def _record_login_failure(client_ip: str | None) -> None:
    module = _ops_ui_module()
    key = _login_bucket_key(client_ip)
    now = monotonic()
    with module._LOGIN_THROTTLE_LOCK:
        attempts = module._LOGIN_FAILED_ATTEMPTS.setdefault(key, deque())
        _prune_login_failures(attempts, now=now)
        attempts.append(now)


def _clear_login_failures(client_ip: str | None) -> None:
    module = _ops_ui_module()
    key = _login_bucket_key(client_ip)
    with module._LOGIN_THROTTLE_LOCK:
        module._LOGIN_FAILED_ATTEMPTS.pop(key, None)


def _is_ops_ui_authenticated(request: Request) -> bool:
    settings = _ops_ui_module().get_settings()
    return is_internal_request_authenticated(
        request,
        expected_token=settings.internal_api_token,
    )
