from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app.services.internal_auth import OPS_UI_SESSION_COOKIE, is_valid_internal_token
from app.services.ops_auth import OpsSessionStateError, issue_ops_ui_session, revoke_ops_ui_session

from .security import (
    _assert_internal_ip_access,
    _assert_same_origin_form_post,
    _auth_state_unavailable_http_error,
    _clear_login_failures,
    _is_login_rate_limited,
    _is_ops_ui_authenticated,
    _ops_ui_module,
    _record_login_failure,
)

router = APIRouter(tags=["ops-ui"])
logger = structlog.get_logger(__name__)


async def _render_page(request: Request, *, page_name: str) -> Response:
    module = _ops_ui_module()
    client_ip = _assert_internal_ip_access(request)
    if not await _is_ops_ui_authenticated(request, client_ip=client_ip):
        return RedirectResponse(url="/ops/login", status_code=303)

    page_path = module.OPS_UI_PAGES[page_name]
    if not page_path.exists():
        raise HTTPException(status_code=503, detail={"code": "E_OPS_UI_ASSET_MISSING"})
    return FileResponse(path=page_path, media_type="text/html")


@router.get("/ops")
async def get_ops_root() -> RedirectResponse:
    return RedirectResponse(url="/ops/promo", status_code=307)


@router.get("/ops/login")
async def get_ops_login_page(request: Request) -> Response:
    module = _ops_ui_module()
    client_ip = _assert_internal_ip_access(request)
    if await _is_ops_ui_authenticated(request, client_ip=client_ip):
        return RedirectResponse(url="/ops/promo", status_code=303)

    if not module.OPS_UI_LOGIN_PAGE.exists():
        raise HTTPException(status_code=503, detail={"code": "E_OPS_UI_ASSET_MISSING"})
    return FileResponse(path=module.OPS_UI_LOGIN_PAGE, media_type="text/html")


@router.post("/ops/login")
async def login_ops_ui(request: Request) -> Response:
    module = _ops_ui_module()
    client_ip = _assert_internal_ip_access(request)
    _assert_same_origin_form_post(request, client_ip=client_ip)
    if _is_login_rate_limited(client_ip):
        logger.warning("ops_ui_auth_failed", reason="login_rate_limited", client_ip=client_ip)
        raise HTTPException(status_code=429, detail={"code": "E_RATE_LIMITED"})

    settings = module.get_settings()
    raw_body = await request.body()
    payload = parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    token = (payload.get("token", [""])[0] or "").strip()
    if not is_valid_internal_token(
        expected_token=settings.internal_api_token, received_token=token
    ):
        _record_login_failure(client_ip)
        await asyncio.sleep(module.OPS_UI_LOGIN_FAILURE_DELAY_SECONDS)
        logger.warning("ops_ui_auth_failed", reason="invalid_token", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    _clear_login_failures(client_ip)
    try:
        session_id = await issue_ops_ui_session(
            settings=settings,
            ttl_seconds=module.OPS_UI_SESSION_MAX_AGE_SECONDS,
        )
    except OpsSessionStateError as exc:
        logger.warning("ops_ui_auth_failed", reason="auth_state_unavailable", client_ip=client_ip)
        raise _auth_state_unavailable_http_error() from exc

    response = RedirectResponse(url="/ops/promo", status_code=303)
    response.set_cookie(
        key=OPS_UI_SESSION_COOKIE,
        value=session_id,
        max_age=module.OPS_UI_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="strict",
        secure=getattr(settings, "app_env", "dev") != "dev",
        path="/",
    )
    return response


@router.post("/ops/logout")
async def logout_ops_ui(request: Request) -> Response:
    client_ip = _assert_internal_ip_access(request)
    _assert_same_origin_form_post(request, client_ip=client_ip)
    settings = _ops_ui_module().get_settings()
    session_id = request.cookies.get(OPS_UI_SESSION_COOKIE)
    try:
        await revoke_ops_ui_session(settings=settings, session_id=session_id)
    except OpsSessionStateError:
        logger.warning("ops_ui_auth_failed", reason="auth_state_unavailable", client_ip=client_ip)
        error_response = JSONResponse(
            status_code=503,
            content={"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}},
        )
        error_response.delete_cookie(key=OPS_UI_SESSION_COOKIE, path="/")
        return error_response
    success_response = RedirectResponse(url="/ops/login", status_code=303)
    success_response.delete_cookie(key=OPS_UI_SESSION_COOKIE, path="/")
    return success_response


@router.get("/ops/promo")
async def get_ops_promo_page(request: Request) -> Response:
    return await _render_page(request, page_name="promo")


@router.get("/ops/referrals")
async def get_ops_referrals_page(request: Request) -> Response:
    return await _render_page(request, page_name="referrals")


@router.get("/ops/notifications")
async def get_ops_notifications_page(request: Request) -> Response:
    return await _render_page(request, page_name="notifications")
