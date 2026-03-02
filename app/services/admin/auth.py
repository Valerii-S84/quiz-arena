from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyotp
import redis.asyncio as redis
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings

ADMIN_ACCESS_COOKIE = "qa_admin_access"
ADMIN_REFRESH_COOKIE = "qa_admin_refresh"
_ADMIN_TOTP_SECRET_KEY = "qa_admin:totp_secret"
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_redis_client: redis.Redis | None = None


@dataclass(frozen=True, slots=True)
class AdminTokenPayload:
    email: str
    role: str
    two_factor_verified: bool
    token_type: str
    expires_at: datetime


class AdminAuthError(ValueError):
    pass


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_password_hash(settings: Settings) -> str:
    hashed = settings.admin_password_hash.strip()
    if hashed:
        return hashed
    fallback_password = settings.admin_password_plain.strip()
    if not fallback_password:
        raise AdminAuthError("ADMIN_PASSWORD_HASH or ADMIN_PASSWORD_PLAIN must be configured")
    return _pwd_context.hash(fallback_password)


def verify_login_credentials(*, settings: Settings, email: str, password: str) -> bool:
    if email.strip().lower() != settings.admin_email.strip().lower():
        return False
    password_hash = _get_password_hash(settings)
    return _pwd_context.verify(password, password_hash)


def build_access_token(
    *,
    settings: Settings,
    email: str,
    role: str = "admin",
    two_factor_verified: bool,
) -> str:
    now = _now_utc()
    expires_at = now + timedelta(minutes=max(1, settings.admin_access_token_ttl_minutes))
    payload = {
        "sub": email,
        "role": role,
        "two_factor": bool(two_factor_verified),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")


def build_refresh_token(*, settings: Settings, email: str, role: str = "admin") -> str:
    now = _now_utc()
    expires_at = now + timedelta(days=max(1, settings.admin_refresh_token_ttl_days))
    payload = {
        "sub": email,
        "role": role,
        "two_factor": True,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.admin_refresh_secret, algorithm="HS256")


def decode_access_token(*, settings: Settings, token: str) -> AdminTokenPayload | None:
    return _decode_token(settings=settings, token=token, token_type="access")


def decode_refresh_token(*, settings: Settings, token: str) -> AdminTokenPayload | None:
    return _decode_token(settings=settings, token=token, token_type="refresh")


def _decode_token(*, settings: Settings, token: str, token_type: str) -> AdminTokenPayload | None:
    if not token:
        return None
    try:
        secret = (
            settings.admin_jwt_secret if token_type == "access" else settings.admin_refresh_secret
        )
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError:
        return None

    payload_type = str(payload.get("type") or "")
    if payload_type != token_type:
        return None

    sub = str(payload.get("sub") or "").strip().lower()
    role = str(payload.get("role") or "")
    exp = payload.get("exp")
    if not sub or not role or not isinstance(exp, (int, float)):
        return None

    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    return AdminTokenPayload(
        email=sub,
        role=role,
        two_factor_verified=bool(payload.get("two_factor", False)),
        token_type=payload_type,
        expires_at=expires_at,
    )


async def get_totp_setup_payload(*, settings: Settings) -> dict[str, str]:
    secret = await get_totp_secret(settings)
    if not secret:
        secret = pyotp.random_base32()
        await set_totp_secret(settings=settings, secret=secret)

    otpauth_uri = pyotp.TOTP(secret).provisioning_uri(
        name=settings.admin_email,
        issuer_name=settings.admin_totp_issuer,
    )
    return {
        "secret": secret,
        "otpauth_uri": otpauth_uri,
    }


async def verify_totp_code(*, settings: Settings, code: str) -> bool:
    secret = await get_totp_secret(settings)
    if not secret:
        return False
    normalized = code.strip().replace(" ", "")
    if not normalized:
        return False
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(normalized, valid_window=1))


async def get_totp_secret(settings: Settings) -> str:
    env_secret = settings.admin_totp_secret.strip()
    if env_secret:
        return env_secret

    client = await _get_redis_client(settings)
    if client is None:
        return ""
    try:
        value = await client.get(_ADMIN_TOTP_SECRET_KEY)
    except Exception:
        return ""
    if isinstance(value, str):
        return value.strip()
    return ""


async def set_totp_secret(*, settings: Settings, secret: str) -> None:
    if settings.admin_totp_secret.strip():
        return
    client = await _get_redis_client(settings)
    if client is None:
        return
    try:
        await client.set(_ADMIN_TOTP_SECRET_KEY, secret)
    except Exception:
        return


async def _get_redis_client(settings: Settings) -> redis.Redis | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        _redis_client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
        await _redis_client.ping()
    except Exception:
        _redis_client = None
    return _redis_client


def apply_auth_cookies(
    *, settings: Settings, response, access_token: str, refresh_token: str
) -> None:
    secure = settings.app_env != "dev"
    response.set_cookie(
        key=ADMIN_ACCESS_COOKIE,
        value=access_token,
        max_age=max(60, settings.admin_access_token_ttl_minutes * 60),
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        key=ADMIN_REFRESH_COOKIE,
        value=refresh_token,
        max_age=max(60, settings.admin_refresh_token_ttl_days * 24 * 3600),
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(key=ADMIN_ACCESS_COOKIE, path="/")
    response.delete_cookie(key=ADMIN_REFRESH_COOKIE, path="/")
