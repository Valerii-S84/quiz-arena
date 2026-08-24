from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.routes.admin import deps as admin_deps
from app.core.config import Settings, get_settings
from app.services.admin import auth as admin_auth
from app.services.admin import auth_authority, auth_refresh_sessions, auth_tokens

from . import auth_helpers, auth_models, auth_responses

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/refresh", response_model=auth_models.SessionResponse)
async def refresh_session(
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    admin_deps.add_admin_noindex_header(response)
    token = (request.cookies.get(admin_auth.ADMIN_REFRESH_COOKIE) or "").strip()
    try:
        payload = await admin_auth.decode_refresh_token(settings=settings, token=token)
    except admin_auth.AdminAuthStateError as exc:
        raise auth_responses.auth_state_unavailable_http_error() from exc
    if payload is None:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    auth_helpers.ensure_allowed_admin_session(
        role=payload.role,
        two_factor_verified=payload.two_factor_verified,
        settings=settings,
    )
    if payload.family_id is None or payload.jti is None:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    try:
        authority = await auth_authority.resolve_current_admin_authority(
            email=payload.email,
            expected_role=payload.role,
        )
    except admin_auth.AdminAuthStateError as exc:
        raise auth_responses.auth_state_unavailable_http_error() from exc
    if authority is None:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    try:
        rotation = await auth_refresh_sessions.rotate_refresh_session(
            settings=settings,
            family_id=payload.family_id,
            jti=payload.jti,
        )
    except admin_auth.AdminAuthStateError as exc:
        raise auth_responses.auth_state_unavailable_http_error() from exc
    if rotation.session is None:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})
    return auth_responses.issue_verified_session_response(
        settings=settings,
        authority=authority,
        refresh_session=rotation.session,
        build_access_token_fn=admin_auth.build_access_token,
        build_refresh_token_fn=admin_auth.build_refresh_token,
        add_noindex_header_fn=admin_deps.add_admin_noindex_header,
        apply_auth_cookies_fn=admin_auth.apply_auth_cookies,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Response:
    admin_deps.add_admin_noindex_header(response)
    access_token = admin_deps.extract_admin_access_token(request)
    refresh_token = (request.cookies.get(admin_auth.ADMIN_REFRESH_COOKIE) or "").strip()
    auth_state_available = True
    try:
        access_revocation = auth_tokens.resolve_access_token_revocation(
            settings=settings,
            token=access_token,
        )
        refresh_payload = await admin_auth.decode_refresh_token(
            settings=settings,
            token=refresh_token,
        )
        await auth_refresh_sessions.revoke_logout_session(
            settings=settings,
            access_revocation=access_revocation,
            refresh_family_id=refresh_payload.family_id if refresh_payload else None,
        )
    except admin_auth.AdminAuthStateError:
        auth_state_available = False
    return auth_responses.build_logout_response(
        auth_state_available=auth_state_available,
        add_noindex_header_fn=admin_deps.add_admin_noindex_header,
        clear_auth_cookies_fn=admin_auth.clear_auth_cookies,
    )


@router.get("/session", response_model=auth_models.SessionResponse)
async def get_session(
    response: Response,
    principal: admin_deps.AdminPrincipal = Depends(admin_deps.get_pending_admin),
    settings: Settings = Depends(get_settings),
) -> auth_models.SessionResponse:
    admin_deps.add_admin_noindex_header(response)
    auth_helpers.ensure_allowed_admin_session(
        role=principal.role,
        two_factor_verified=principal.two_factor_verified,
        settings=settings,
    )
    return auth_models.SessionResponse(
        email=principal.email,
        role=principal.role,
        two_factor_verified=principal.two_factor_verified,
    )
