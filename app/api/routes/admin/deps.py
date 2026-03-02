from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.services.admin.auth import decode_access_token
from app.services.internal_auth import extract_client_ip


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    email: str
    role: str
    two_factor_verified: bool
    client_ip: str | None


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        return ""
    return auth_header[7:].strip()


def _extract_access_token(request: Request) -> str:
    cookie_token = (request.cookies.get("qa_admin_access") or "").strip()
    if cookie_token:
        return cookie_token
    return _extract_bearer_token(request)


def add_admin_noindex_header(response: Response) -> None:
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


async def get_pending_admin(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AdminPrincipal:
    add_admin_noindex_header(response)
    token = _extract_access_token(request)
    payload = decode_access_token(settings=settings, token=token)
    if payload is None:
        raise HTTPException(status_code=401, detail={"code": "E_UNAUTHORIZED"})

    return AdminPrincipal(
        email=payload.email,
        role=payload.role,
        two_factor_verified=payload.two_factor_verified,
        client_ip=extract_client_ip(
            request,
            trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
        ),
    )


async def get_current_admin(
    principal: AdminPrincipal = Depends(get_pending_admin),
) -> AdminPrincipal:
    if principal.role != "admin" or not principal.two_factor_verified:
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    return principal
