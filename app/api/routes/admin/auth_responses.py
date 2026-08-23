from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.services.admin.auth_authority import CurrentAdminAuthority
from app.services.admin.auth_refresh_sessions import RefreshSessionIdentity


def auth_state_unavailable_http_error() -> HTTPException:
    return HTTPException(status_code=503, detail={"code": "E_AUTH_STATE_UNAVAILABLE"})


def build_login_success_response(
    *,
    settings: Settings,
    access_token: str,
    refresh_token: str,
    add_noindex_header_fn,
    apply_auth_cookies_fn,
) -> JSONResponse:
    response = JSONResponse(content={"requires_2fa": False})
    add_noindex_header_fn(response)
    apply_auth_cookies_fn(
        settings=settings,
        response=response,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return response


def issue_login_success_response(
    *,
    settings: Settings,
    authority: CurrentAdminAuthority,
    refresh_session: RefreshSessionIdentity,
    build_access_token_fn,
    build_refresh_token_fn,
    add_noindex_header_fn,
    apply_auth_cookies_fn,
) -> JSONResponse:
    return build_login_success_response(
        settings=settings,
        access_token=build_access_token_fn(
            settings=settings,
            email=authority.email,
            role=authority.role,
            two_factor_verified=True,
        ),
        refresh_token=build_refresh_token_fn(
            settings=settings,
            email=authority.email,
            role=authority.role,
            jti=refresh_session.jti,
            family_id=refresh_session.family_id,
        ),
        add_noindex_header_fn=add_noindex_header_fn,
        apply_auth_cookies_fn=apply_auth_cookies_fn,
    )


def build_partial_login_response(
    *,
    settings: Settings,
    access_token: str,
    add_noindex_header_fn,
    set_partial_access_cookie_fn,
) -> JSONResponse:
    response = JSONResponse(content={"requires_2fa": True})
    add_noindex_header_fn(response)
    set_partial_access_cookie_fn(
        settings=settings,
        response=response,
        access_token=access_token,
    )
    return response


def build_verified_session_response(
    *,
    settings: Settings,
    email: str,
    role: str,
    access_token: str,
    refresh_token: str,
    add_noindex_header_fn,
    apply_auth_cookies_fn,
) -> JSONResponse:
    response = JSONResponse(
        content={
            "email": email,
            "role": role,
            "two_factor_verified": True,
        }
    )
    add_noindex_header_fn(response)
    apply_auth_cookies_fn(
        settings=settings,
        response=response,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return response


def issue_verified_session_response(
    *,
    settings: Settings,
    authority: CurrentAdminAuthority,
    refresh_session: RefreshSessionIdentity,
    build_access_token_fn,
    build_refresh_token_fn,
    add_noindex_header_fn,
    apply_auth_cookies_fn,
) -> JSONResponse:
    return build_verified_session_response(
        settings=settings,
        email=authority.email,
        role=authority.role,
        access_token=build_access_token_fn(
            settings=settings,
            email=authority.email,
            role=authority.role,
            two_factor_verified=True,
        ),
        refresh_token=build_refresh_token_fn(
            settings=settings,
            email=authority.email,
            role=authority.role,
            jti=refresh_session.jti,
            family_id=refresh_session.family_id,
        ),
        add_noindex_header_fn=add_noindex_header_fn,
        apply_auth_cookies_fn=apply_auth_cookies_fn,
    )


def build_logout_response(
    *,
    auth_state_available: bool,
    add_noindex_header_fn,
    clear_auth_cookies_fn,
) -> JSONResponse:
    response = (
        JSONResponse(content={"ok": True})
        if auth_state_available
        else JSONResponse(
            status_code=503,
            content={"detail": {"code": "E_AUTH_STATE_UNAVAILABLE"}},
        )
    )
    add_noindex_header_fn(response)
    clear_auth_cookies_fn(response)
    return response


__all__ = [
    "auth_state_unavailable_http_error",
    "build_partial_login_response",
    "build_login_success_response",
    "build_logout_response",
    "build_verified_session_response",
    "issue_login_success_response",
    "issue_verified_session_response",
]
