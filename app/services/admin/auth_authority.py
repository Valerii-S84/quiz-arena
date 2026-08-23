from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError

from app.db.models.admins import Admin
from app.db.repo.admins_repo import AdminsRepo
from app.db.session import SessionLocal

from .auth_common import AdminAuthStateError

ALLOWED_ADMIN_ROLES = frozenset({"admin", "super_admin"})


@dataclass(frozen=True, slots=True)
class CurrentAdminAuthority:
    id: UUID
    email: str
    role: str
    enabled: bool


def normalize_admin_role(raw_role: str) -> str:
    return raw_role.strip().lower().replace("-", "_")


def _resolved_authority(
    *,
    admin: Admin,
    expected_email: str,
    expected_role: str | None,
) -> CurrentAdminAuthority | None:
    email = admin.email.strip().lower()
    role = normalize_admin_role(admin.role)
    if (
        not isinstance(admin.id, UUID)
        or email != expected_email
        or role not in ALLOWED_ADMIN_ROLES
        or (expected_role is not None and role != expected_role)
        or admin.enabled is not True
    ):
        return None
    return CurrentAdminAuthority(
        id=admin.id,
        email=email,
        role=role,
        enabled=True,
    )


async def resolve_current_admin_authority(
    *,
    email: str,
    expected_role: str | None = None,
) -> CurrentAdminAuthority | None:
    normalized_email = email.strip().lower()
    normalized_role = None if expected_role is None else normalize_admin_role(expected_role)
    if not normalized_email or (
        normalized_role is not None and normalized_role not in ALLOWED_ADMIN_ROLES
    ):
        return None

    try:
        async with SessionLocal.begin() as session:
            try:
                admin = await AdminsRepo.get_by_email(session, email=normalized_email)
            except MultipleResultsFound:
                return None
            if admin is None:
                return None
            return _resolved_authority(
                admin=admin,
                expected_email=normalized_email,
                expected_role=normalized_role,
            )
    except MultipleResultsFound:
        return None
    except SQLAlchemyError as exc:
        raise AdminAuthStateError("Admin authority store is unavailable") from exc


__all__ = [
    "ALLOWED_ADMIN_ROLES",
    "CurrentAdminAuthority",
    "normalize_admin_role",
    "resolve_current_admin_authority",
]
