from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import Settings

from .auth_common import AdminTokenPayload, _auth_state_unavailable, _now_utc
from .auth_state import _require_redis_client, _revoked_token_key, is_token_revoked


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


async def decode_access_token(*, settings: Settings, token: str) -> AdminTokenPayload | None:
    return await _decode_token(settings=settings, token=token, token_type="access")


async def decode_refresh_token(*, settings: Settings, token: str) -> AdminTokenPayload | None:
    return await _decode_token(settings=settings, token=token, token_type="refresh")


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
    return AdminTokenPayload(
        email=sub,
        role=role,
        two_factor_verified=bool(payload.get("two_factor", False)),
        token_type=payload_type,
        expires_at=expires_at,
    )


async def revoke_access_token(*, settings: Settings, token: str) -> None:
    await _revoke_token(settings=settings, token=token, token_type="access")


async def revoke_refresh_token(*, settings: Settings, token: str) -> None:
    await _revoke_token(settings=settings, token=token, token_type="refresh")


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
