from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlsplit

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.core.config import get_settings
from app.services.internal_auth import (
    OPS_UI_SESSION_COOKIE,
    build_ops_ui_session_value,
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_request_authenticated,
    is_valid_internal_token,
)

router = APIRouter(tags=["ops-ui"])
logger = structlog.get_logger(__name__)

OPS_UI_ROOT = Path(__file__).resolve().parents[2] / "ops_ui" / "site"
OPS_UI_STATIC_DIR = OPS_UI_ROOT / "static"
OPS_UI_LOGIN_PAGE = OPS_UI_ROOT / "login.html"
OPS_UI_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
OPS_UI_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
OPS_UI_LOGIN_FAILED_WINDOW_SECONDS = 5 * 60
OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS = 8
OPS_UI_LOGIN_FAILURE_DELAY_SECONDS = 0.4
OPS_UI_PAGES = {
    "promo": OPS_UI_ROOT / "promo.html",
    "referrals": OPS_UI_ROOT / "referrals.html",
    "notifications": OPS_UI_ROOT / "notifications.html",
}
_LOGIN_FAILED_ATTEMPTS: dict[str, deque[float]] = {}
_LOGIN_THROTTLE_LOCK = Lock()


def _assert_internal_ip_access(request: Request) -> str | None:
    settings = get_settings()
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
    content_type = (request.headers.get("content-type") or "").split(";", maxsplit=1)[0].strip().lower()
    if content_type != OPS_UI_FORM_CONTENT_TYPE:
        logger.warning("ops_ui_auth_failed", reason="invalid_form_content_type", client_ip=client_ip)
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
        logger.warning("ops_ui_auth_failed", reason="origin_mismatch", client_ip=client_ip, origin=origin)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    referer = _normalized_origin(request.headers.get("referer"))
    if referer not in allowed_origins:
        logger.warning("ops_ui_auth_failed", reason="referer_mismatch", client_ip=client_ip, referer=referer)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


def _login_bucket_key(client_ip: str | None) -> str:
    return client_ip or "unknown"


def _prune_login_failures(attempts: deque[float], *, now: float) -> None:
    cutoff = now - OPS_UI_LOGIN_FAILED_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()


def _is_login_rate_limited(client_ip: str | None) -> bool:
    key = _login_bucket_key(client_ip)
    now = monotonic()
    with _LOGIN_THROTTLE_LOCK:
        attempts = _LOGIN_FAILED_ATTEMPTS.get(key)
        if attempts is None:
            return False
        _prune_login_failures(attempts, now=now)
        if not attempts:
            _LOGIN_FAILED_ATTEMPTS.pop(key, None)
            return False
        return len(attempts) >= OPS_UI_LOGIN_MAX_FAILED_ATTEMPTS


def _record_login_failure(client_ip: str | None) -> None:
    key = _login_bucket_key(client_ip)
    now = monotonic()
    with _LOGIN_THROTTLE_LOCK:
        attempts = _LOGIN_FAILED_ATTEMPTS.setdefault(key, deque())
        _prune_login_failures(attempts, now=now)
        attempts.append(now)


def _clear_login_failures(client_ip: str | None) -> None:
    key = _login_bucket_key(client_ip)
    with _LOGIN_THROTTLE_LOCK:
        _LOGIN_FAILED_ATTEMPTS.pop(key, None)


def _is_ops_ui_authenticated(request: Request) -> bool:
    settings = get_settings()
    return is_internal_request_authenticated(
        request,
        expected_token=settings.internal_api_token,
    )


def _render_page(request: Request, *, page_name: str) -> Response:
    _assert_internal_ip_access(request)
    if not _is_ops_ui_authenticated(request):
        return RedirectResponse(url="/ops/login", status_code=303)

    page_path = OPS_UI_PAGES[page_name]
    if not page_path.exists():
        raise HTTPException(status_code=503, detail={"code": "E_OPS_UI_ASSET_MISSING"})
    return FileResponse(path=page_path, media_type="text/html")


@router.get("/ops")
async def get_ops_root() -> RedirectResponse:
    return RedirectResponse(url="/ops/promo", status_code=307)


@router.get("/ops/login")
async def get_ops_login_page(request: Request) -> Response:
    _assert_internal_ip_access(request)
    if _is_ops_ui_authenticated(request):
        return RedirectResponse(url="/ops/promo", status_code=303)

    if not OPS_UI_LOGIN_PAGE.exists():
        raise HTTPException(status_code=503, detail={"code": "E_OPS_UI_ASSET_MISSING"})
    return FileResponse(path=OPS_UI_LOGIN_PAGE, media_type="text/html")


@router.post("/ops/login")
async def login_ops_ui(request: Request) -> Response:
    client_ip = _assert_internal_ip_access(request)
    _assert_same_origin_form_post(request, client_ip=client_ip)
    if _is_login_rate_limited(client_ip):
        logger.warning("ops_ui_auth_failed", reason="login_rate_limited", client_ip=client_ip)
        raise HTTPException(status_code=429, detail={"code": "E_RATE_LIMITED"})

    settings = get_settings()
    raw_body = await request.body()
    payload = parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    token = (payload.get("token", [""])[0] or "").strip()
    if not is_valid_internal_token(expected_token=settings.internal_api_token, received_token=token):
        _record_login_failure(client_ip)
        await asyncio.sleep(OPS_UI_LOGIN_FAILURE_DELAY_SECONDS)
        logger.warning("ops_ui_auth_failed", reason="invalid_token", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    _clear_login_failures(client_ip)

    response = RedirectResponse(url="/ops/promo", status_code=303)
    response.set_cookie(
        key=OPS_UI_SESSION_COOKIE,
        value=build_ops_ui_session_value(token=settings.internal_api_token),
        max_age=OPS_UI_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="strict",
        secure=getattr(settings, "app_env", "dev") != "dev",
        path="/ops",
    )
    return response


@router.post("/ops/logout")
async def logout_ops_ui(request: Request) -> RedirectResponse:
    client_ip = _assert_internal_ip_access(request)
    _assert_same_origin_form_post(request, client_ip=client_ip)
    response = RedirectResponse(url="/ops/login", status_code=303)
    response.delete_cookie(key=OPS_UI_SESSION_COOKIE, path="/ops")
    return response


@router.get("/ops/promo")
async def get_ops_promo_page(request: Request) -> Response:
    return _render_page(request, page_name="promo")


@router.get("/ops/referrals")
async def get_ops_referrals_page(request: Request) -> Response:
    return _render_page(request, page_name="referrals")


@router.get("/ops/notifications")
async def get_ops_notifications_page(request: Request) -> Response:
    return _render_page(request, page_name="notifications")
