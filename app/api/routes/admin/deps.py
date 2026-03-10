from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.db.repo.admins_repo import AdminsRepo
from app.db.session import SessionLocal
from app.services.admin.auth import decode_access_token
from app.services.internal_auth import extract_client_ip

ALLOWED_ADMIN_ROLES = frozenset({"admin", "super_admin"})


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    id: UUID
    email: str
    role: str
    two_factor_verified: bool
    client_ip: str | None

    @property
    def is_super_admin(self) -> bool:
        return normalize_admin_role(self.role) == "super_admin"


def normalize_admin_role(raw_role: str) -> str:
    return raw_role.strip().lower().replace("-", "_")


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

    normalized_email = payload.email.strip().lower()
    normalized_role = normalize_admin_role(payload.role)
    async with SessionLocal.begin() as session:
        admin = await AdminsRepo.get_or_create(
            session,
            email=normalized_email,
            role=normalized_role if normalized_role in ALLOWED_ADMIN_ROLES else "admin",
        )

    return AdminPrincipal(
        id=admin.id,
        email=normalized_email,
        role=normalized_role,
        two_factor_verified=payload.two_factor_verified,
        client_ip=extract_client_ip(
            request,
            trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
        ),
    )


async def get_current_admin(
    principal: AdminPrincipal = Depends(get_pending_admin),
    settings: Settings = Depends(get_settings),
) -> AdminPrincipal:
    if normalize_admin_role(principal.role) not in ALLOWED_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    if settings.admin_2fa_required and not principal.two_factor_verified:
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})
    return principal
