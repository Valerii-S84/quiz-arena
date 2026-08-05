from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import Settings

from .auth_common import AdminAuthError, AdminTokenPayload, _auth_state_unavailable, _now_utc
from .auth_state import _require_redis_client, _revoked_token_key, is_token_revoked

_REFRESH_SESSION_CLAIM_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")


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


def build_refresh_token(
    *,
    settings: Settings,
    email: str,
    jti: str,
    family_id: str,
    role: str = "admin",
) -> str:
    normalized_jti = _normalize_refresh_session_claim(jti)
    normalized_family_id = _normalize_refresh_session_claim(family_id)
    if normalized_jti is None or normalized_family_id is None:
        raise AdminAuthError("Refresh session identity is invalid")
    now = _now_utc()
    expires_at = now + timedelta(days=max(1, settings.admin_refresh_token_ttl_days))
    payload = {
        "sub": email,
        "role": role,
        "two_factor": True,
        "type": "refresh",
        "jti": normalized_jti,
        "family_id": normalized_family_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.admin_refresh_secret, algorithm="HS256")


async def decode_access_token(*, settings: Settings, token: str) -> AdminTokenPayload | None:
    return await _decode_token(settings=settings, token=token, token_type="access")


async def decode_refresh_token(*, settings: Settings, token: str) -> AdminTokenPayload | None:
    return _decode_token_payload(settings=settings, token=token, token_type="refresh")


def _normalize_refresh_session_claim(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if _REFRESH_SESSION_CLAIM_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def _decode_token_payload(
    *,
    settings: Settings,
    token: str,
    token_type: str,
) -> AdminTokenPayload | None:
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
    jti = None
    family_id = None
    if token_type == "refresh":
        jti = _normalize_refresh_session_claim(payload.get("jti"))
        family_id = _normalize_refresh_session_claim(payload.get("family_id"))
        if jti is None or family_id is None:
            return None
    return AdminTokenPayload(
        email=sub,
        role=role,
        two_factor_verified=bool(payload.get("two_factor", False)),
        token_type=payload_type,
        expires_at=expires_at,
        jti=jti,
        family_id=family_id,
    )


async def revoke_access_token(*, settings: Settings, token: str) -> None:
    await _revoke_token(settings=settings, token=token, token_type="access")


async def _decode_token(
    *, settings: Settings, token: str, token_type: str
) -> AdminTokenPayload | None:
    payload = _decode_token_payload(settings=settings, token=token, token_type=token_type)
    if payload is None:
        return None
    if await is_token_revoked(settings=settings, token=token):
        return None
    return payload


async def _revoke_token(*, settings: Settings, token: str, token_type: str) -> None:
    payload = _decode_token_payload(settings=settings, token=token, token_type=token_type)
    if payload is None:
        return

    ttl_seconds = int((payload.expires_at - _now_utc()).total_seconds())
    if ttl_seconds <= 0:
        return

    client = await _require_redis_client(settings)
    try:
        await client.set(_revoked_token_key(token), "1", ex=max(1, ttl_seconds))
    except Exception as exc:
        raise _auth_state_unavailable() from exc
