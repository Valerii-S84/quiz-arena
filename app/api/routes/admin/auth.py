from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.routes.admin import deps as admin_deps
from app.core.config import Settings, get_settings
from app.services.admin import auth as admin_auth
from app.services.admin import rate_limit as admin_rate_limit

from . import auth_helpers, auth_models, auth_responses

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=auth_models.LoginResponse)
async def login_admin(
    payload: auth_models.LoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    bucket = auth_helpers.rate_limit_bucket(request=request, settings=settings)
    window_seconds = auth_helpers.login_rate_limit_window_seconds(settings)
    auth_helpers.ensure_not_rate_limited(
        bucket=bucket,
        settings=settings,
        is_rate_limited_fn=admin_rate_limit.is_rate_limited,
    )

    if not admin_auth.verify_login_credentials(
        settings=settings, email=payload.email, password=payload.password
    ):
        admin_rate_limit.record_failure(bucket=bucket, window_seconds=window_seconds)
        raise HTTPException(status_code=401, detail={"code": "E_INVALID_CREDENTIALS"})

    admin_rate_limit.clear_failures(bucket=bucket)
    if not settings.admin_2fa_required:
        return auth_responses.issue_login_success_response(
            settings=settings,
            email=payload.email.lower(),
            role=auth_helpers.configured_admin_role(settings),
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
    bucket = auth_helpers.rate_limit_bucket(request=request, settings=settings)
    window_seconds = auth_helpers.login_rate_limit_window_seconds(settings)
    auth_helpers.ensure_not_rate_limited(
        bucket=bucket,
        settings=settings,
        is_rate_limited_fn=admin_rate_limit.is_rate_limited,
    )

    if settings.admin_2fa_required:
        try:
            is_valid_totp = await admin_auth.verify_totp_code(
                settings=settings,
                code=payload.code,
            )
        except admin_auth.AdminAuthStateError as exc:
            raise auth_responses.auth_state_unavailable_http_error() from exc
        if not is_valid_totp:
            admin_rate_limit.record_failure(bucket=bucket, window_seconds=window_seconds)
            raise HTTPException(status_code=401, detail={"code": "E_INVALID_TOTP"})

    admin_rate_limit.clear_failures(bucket=bucket)
    return auth_responses.issue_verified_session_response(
        settings=settings,
        email=principal.email,
        role=principal.role,
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
        return await admin_auth.get_totp_setup_payload(settings=settings)
    except admin_auth.AdminAuthStateError as exc:
        raise auth_responses.auth_state_unavailable_http_error() from exc
