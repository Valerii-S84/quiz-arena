from __future__ import annotations

import hashlib

import redis.asyncio as redis

from app.core.config import Settings

from .auth_common import _auth_state_unavailable

_ADMIN_TOTP_SECRET_KEY = "qa_admin:totp_secret"
_ADMIN_REVOKED_TOKEN_KEY_PREFIX = "qa_admin:revoked_token:"
_redis_client: redis.Redis | None = None


def _revoked_token_key(token: str) -> str:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{_ADMIN_REVOKED_TOKEN_KEY_PREFIX}{token_hash}"


async def is_token_revoked(*, settings: Settings, token: str) -> bool:
    if not token:
        return False
    client = await _require_redis_client(settings)
    try:
        value = await client.get(_revoked_token_key(token))
    except Exception as exc:
        raise _auth_state_unavailable() from exc
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


async def get_totp_secret(settings: Settings, *, strict: bool = False) -> str:
    env_secret = settings.admin_totp_secret.strip()
    if env_secret:
        return env_secret

    client = await _get_redis_client(settings)
    if client is None:
        if strict:
            raise _auth_state_unavailable()
        return ""
    try:
        value = await client.get(_ADMIN_TOTP_SECRET_KEY)
    except Exception as exc:
        if strict:
            raise _auth_state_unavailable() from exc
        return ""
    if isinstance(value, str):
        return value.strip()
    return ""


async def set_totp_secret(*, settings: Settings, secret: str, strict: bool = False) -> None:
    if settings.admin_totp_secret.strip():
        return
    client = await _get_redis_client(settings)
    if client is None:
        if strict:
            raise _auth_state_unavailable()
        return
    try:
        await client.set(_ADMIN_TOTP_SECRET_KEY, secret)
    except Exception as exc:
        if strict:
            raise _auth_state_unavailable() from exc
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


async def _require_redis_client(settings: Settings) -> redis.Redis:
    client = await _get_redis_client(settings)
    if client is None:
        raise _auth_state_unavailable()
    return client
