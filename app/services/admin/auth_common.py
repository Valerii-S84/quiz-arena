from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from passlib.context import CryptContext

from app.core.config import Settings

ADMIN_ACCESS_COOKIE = "qa_admin_access"
ADMIN_REFRESH_COOKIE = "qa_admin_refresh"
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass(frozen=True, slots=True)
class AdminTokenPayload:
    email: str
    role: str
    two_factor_verified: bool
    token_type: str
    expires_at: datetime
    jti: str | None = None
    family_id: str | None = None


class AdminAuthError(ValueError):
    pass


class AdminAuthStateError(RuntimeError):
    pass


def _auth_state_unavailable() -> AdminAuthStateError:
    return AdminAuthStateError("Admin auth state store is unavailable")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_password_hash(settings: Settings) -> str:
    hashed = (settings.admin_password_hash or "").strip()
    if hashed:
        return hashed
    fallback_password = (settings.admin_password_plain or "").strip()
    if not fallback_password:
        raise AdminAuthError("ADMIN_PASSWORD_HASH or ADMIN_PASSWORD_PLAIN must be configured")
    return _pwd_context.hash(fallback_password)


def verify_login_credentials(*, settings: Settings, email: str, password: str) -> bool:
    if email.strip().lower() != settings.admin_email.strip().lower():
        return False
    password_hash = _get_password_hash(settings)
    return _pwd_context.verify(password, password_hash)
