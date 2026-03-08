from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.api.routes.admin.deps import (
    ALLOWED_ADMIN_ROLES,
    AdminPrincipal,
    add_admin_noindex_header,
    get_pending_admin,
    normalize_admin_role,
)
from app.core.config import Settings, get_settings
from app.services.admin.auth import (
    apply_auth_cookies,
    build_access_token,
    build_refresh_token,
    clear_auth_cookies,
    decode_refresh_token,
    get_totp_setup_payload,
    verify_login_credentials,
    verify_totp_code,
)
from app.services.admin.rate_limit import clear_failures, is_rate_limited, record_failure

from .auth_helpers import configured_admin_role, rate_limit_bucket, set_partial_access_cookie
from .auth_models import LoginRequest, LoginResponse, SessionResponse, Verify2FARequest

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=LoginResponse)
async def login_admin(
    payload: LoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    bucket = rate_limit_bucket(request=request, settings=settings)
    window_seconds = settings.admin_login_rate_limit_window_minutes * 60
    if is_rate_limited(
        bucket=bucket,
        limit=settings.admin_login_rate_limit_attempts,
        window_seconds=window_seconds,
    ):
        raise HTTPException(status_code=429, detail={"code": "E_RATE_LIMITED"})

    if not verify_login_credentials(
        settings=settings, email=payload.email, password=payload.password
    ):
        record_failure(bucket=bucket, window_seconds=window_seconds)
        raise HTTPException(status_code=401, detail={"code": "E_INVALID_CREDENTIALS"})

    clear_failures(bucket=bucket)
    if not settings.admin_2fa_required:
        full_access_token = build_access_token(
            settings=settings,
            email=payload.email.lower(),
            role=configured_admin_role(settings),
            two_factor_verified=True,
        )
        full_refresh_token = build_refresh_token(
            settings=settings,
            email=payload.email.lower(),
            role=configured_admin_role(settings),
        )
        full_response = JSONResponse(content={"requires_2fa": False})
        add_admin_noindex_header(full_response)
        apply_auth_cookies(
            settings=settings,
            response=full_response,
            access_token=full_access_token,
            refresh_token=full_refresh_token,
        )
        return full_response

    access_token = build_access_token(
        settings=settings,
        email=payload.email.lower(),
        role=configured_admin_role(settings),
        two_factor_verified=False,
    )
    response = JSONResponse(content={"requires_2fa": True})
    add_admin_noindex_header(response)
    set_partial_access_cookie(settings=settings, response=response, access_token=access_token)
    return response


@router.post("/2fa/verify")
async def verify_2fa(
    payload: Verify2FARequest,
    request: Request,
    response: Response,
    principal: AdminPrincipal = Depends(get_pending_admin),
    settings: Settings = Depends(get_settings),
) -> Response:
    add_admin_noindex_header(response)
    bucket = rate_limit_bucket(request=request, settings=settings)
    window_seconds = settings.admin_login_rate_limit_window_minutes * 60
    if is_rate_limited(
        bucket=bucket,
        limit=settings.admin_login_rate_limit_attempts,
        window_seconds=window_seconds,
    ):
        raise HTTPException(status_code=429, detail={"code": "E_RATE_LIMITED"})

    if settings.admin_2fa_required and not await verify_totp_code(
        settings=settings,
        code=payload.code,
    ):
        record_failure(bucket=bucket, window_seconds=window_seconds)
        raise HTTPException(status_code=401, detail={"code": "E_INVALID_TOTP"})

    clear_failures(bucket=bucket)
    access_token = build_access_token(
        settings=settings,
        email=principal.email,
        role=principal.role,
        two_factor_verified=True,
    )
    refresh_token = build_refresh_token(
        settings=settings, email=principal.email, role=principal.role
    )

    full_response = JSONResponse(
        content={
            "email": principal.email,
            "role": principal.role,
            "two_factor_verified": True,
        }
    )
    add_admin_noindex_header(full_response)
    apply_auth_cookies(
        settings=settings,
        response=full_response,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return full_response


@router.get("/2fa/setup")
async def setup_2fa(
    response: Response,
    _principal: AdminPrincipal = Depends(get_pending_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    add_admin_noindex_header(response)
    return await get_totp_setup_payload(settings=settings)


@router.post("/refresh", response_model=SessionResponse)
async def refresh_session(
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    add_admin_noindex_header(response)
    token = (request.cookies.get("qa_admin_refresh") or "").strip()
    payload = decode_refresh_token(settings=settings, token=token)
    if payload is None or normalize_admin_role(payload.role) not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    if settings.admin_2fa_required and not payload.two_factor_verified:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})

    access_token = build_access_token(
        settings=settings,
        email=payload.email,
        role=payload.role,
        two_factor_verified=True,
    )
    refresh_token = build_refresh_token(settings=settings, email=payload.email, role=payload.role)
    refreshed = JSONResponse(
        content={
            "email": payload.email,
            "role": payload.role,
            "two_factor_verified": True,
        }
    )
    add_admin_noindex_header(refreshed)
    apply_auth_cookies(
        settings=settings,
        response=refreshed,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return refreshed


@router.post("/logout")
async def logout(response: Response) -> Response:
    add_admin_noindex_header(response)
    logout_response = JSONResponse(content={"ok": True})
    add_admin_noindex_header(logout_response)
    clear_auth_cookies(logout_response)
    return logout_response


@router.get("/session", response_model=SessionResponse)
async def get_session(
    response: Response,
    principal: AdminPrincipal = Depends(get_pending_admin),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    add_admin_noindex_header(response)
    if normalize_admin_role(principal.role) not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    if settings.admin_2fa_required and not principal.two_factor_verified:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    return SessionResponse(
        email=principal.email,
        role=principal.role,
        two_factor_verified=principal.two_factor_verified,
    )
