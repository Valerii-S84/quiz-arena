from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.routes.admin import deps as admin_deps
from app.core.config import Settings, get_settings
from app.services.admin import auth as admin_auth
from app.services.admin import auth_refresh_sessions
from app.services.admin import rate_limit as _admin_rate_limit

from . import auth_helpers, auth_models, auth_rate_limit, auth_responses

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
admin_rate_limit = _admin_rate_limit


@router.post("/login", response_model=auth_models.LoginResponse)
async def login_admin(
    payload: auth_models.LoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    buckets = await auth_rate_limit.ensure_login_allowed(
        request=request,
        settings=settings,
        email=payload.email,
    )
    window_seconds = auth_helpers.login_rate_limit_window_seconds(settings)

    if not admin_auth.verify_login_credentials(
        settings=settings, email=payload.email, password=payload.password
    ):
        await auth_rate_limit.record_failure(
            settings=settings,
            buckets=buckets,
            window_seconds=window_seconds,
            action="login",
        )
        raise HTTPException(status_code=401, detail={"code": "E_INVALID_CREDENTIALS"})

    await auth_rate_limit.clear_failures(settings=settings, buckets=buckets, action="login")
    if not settings.admin_2fa_required:
        try:
            refresh_session = await auth_refresh_sessions.create_refresh_session(settings=settings)
        except admin_auth.AdminAuthStateError as exc:
            raise auth_responses.auth_state_unavailable_http_error() from exc
        return auth_responses.issue_login_success_response(
            settings=settings,
            email=payload.email.lower(),
            role=auth_helpers.configured_admin_role(settings),
            refresh_session=refresh_session,
            build_access_token_fn=admin_auth.build_access_token,
            build_refresh_token_fn=admin_auth.build_refresh_token,
            add_noindex_header_fn=admin_deps.add_admin_noindex_header,
            apply_auth_cookies_fn=admin_auth.apply_auth_cookies,
        )

    access_token = admin_auth.build_access_token(
        settings=settings,
        email=payload.email.lower(),
        role=auth_helpers.configured_admin_role(settings),
        two_factor_verified=False,
    )
    return auth_responses.build_partial_login_response(
        settings=settings,
        access_token=access_token,
        add_noindex_header_fn=admin_deps.add_admin_noindex_header,
        set_partial_access_cookie_fn=auth_helpers.set_partial_access_cookie,
    )


@router.post("/2fa/verify")
async def verify_2fa(
    payload: auth_models.Verify2FARequest,
    request: Request,
    response: Response,
    principal: admin_deps.AdminPrincipal = Depends(admin_deps.get_pending_admin),
    settings: Settings = Depends(get_settings),
) -> Response:
    admin_deps.add_admin_noindex_header(response)
    buckets = await auth_rate_limit.ensure_verify_2fa_allowed(
        request=request,
        settings=settings,
        email=principal.email,
    )
    window_seconds = auth_helpers.login_rate_limit_window_seconds(settings)

    if settings.admin_2fa_required:
        try:
            is_valid_totp = await admin_auth.verify_totp_code(
                settings=settings,
                code=payload.code,
            )
        except admin_auth.AdminAuthStateError as exc:
            raise auth_responses.auth_state_unavailable_http_error() from exc
        if not is_valid_totp:
            await auth_rate_limit.record_failure(
                settings=settings,
                buckets=buckets,
                window_seconds=window_seconds,
                action="verify_2fa",
            )
            raise HTTPException(status_code=401, detail={"code": "E_INVALID_TOTP"})

    await auth_rate_limit.clear_failures(settings=settings, buckets=buckets, action="verify_2fa")
    try:
        refresh_session = await auth_refresh_sessions.create_refresh_session(settings=settings)
    except admin_auth.AdminAuthStateError as exc:
        raise auth_responses.auth_state_unavailable_http_error() from exc
    return auth_responses.issue_verified_session_response(
        settings=settings,
        email=principal.email,
        role=principal.role,
        refresh_session=refresh_session,
        build_access_token_fn=admin_auth.build_access_token,
        build_refresh_token_fn=admin_auth.build_refresh_token,
        add_noindex_header_fn=admin_deps.add_admin_noindex_header,
        apply_auth_cookies_fn=admin_auth.apply_auth_cookies,
    )


@router.get("/2fa/setup")
async def setup_2fa(
    response: Response,
    _principal: admin_deps.AdminPrincipal = Depends(admin_deps.get_pending_admin),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    admin_deps.add_admin_noindex_header(response)
    try:
        payload = await admin_auth.get_totp_setup_payload(settings=settings)
    except admin_auth.AdminAuthStateError as exc:
        raise auth_responses.auth_state_unavailable_http_error() from exc
    if payload is None:
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    return payload
