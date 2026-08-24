from __future__ import annotations

import secrets
from collections.abc import Awaitable
from dataclasses import dataclass
from enum import Enum

import structlog

from app.core.config import Settings

from .auth_common import AdminAuthStateError, _auth_state_unavailable
from .auth_state import _require_redis_client
from .auth_tokens import AccessTokenRevocation

_REFRESH_FAMILY_KEY_PREFIX = "qa_admin:refresh_family:"
_REVOKED_STATE = "revoked"
_LOGOUT_ACCESS_PLACEHOLDER_KEY = "qa_admin:logout:no_access"
_LOGOUT_REFRESH_PLACEHOLDER_KEY = "qa_admin:logout:no_refresh"

logger = structlog.get_logger(__name__)

_ROTATE_REFRESH_SESSION_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
  return 2
end
if current == ARGV[3] then
  return 3
end

local function revoke_family()
  local ttl = redis.call('TTL', KEYS[1])
  if ttl < 1 then
    ttl = tonumber(ARGV[4])
  end
  redis.call('SET', KEYS[1], ARGV[3], 'EX', ttl)
end

if current ~= ARGV[1] then
  revoke_family()
  return 4
end

redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[4])
return 1
"""

_REVOKE_LOGOUT_SESSION_SCRIPT = """
if ARGV[1] == '1' then
  redis.call('SET', KEYS[1], '1', 'EX', ARGV[2])
end
if ARGV[3] == '1' then
  local ttl = redis.call('TTL', KEYS[2])
  if ttl < 1 then ttl = tonumber(ARGV[4]) end
  redis.call('SET', KEYS[2], ARGV[5], 'EX', ttl)
end
return 1
"""


@dataclass(frozen=True, slots=True)
class RefreshSessionIdentity:
    family_id: str
    jti: str


class RefreshRotationStatus(str, Enum):
    ROTATED = "rotated"
    MISSING = "missing"
    REVOKED = "revoked"
    REPLAY = "replay"


@dataclass(frozen=True, slots=True)
class RefreshRotationResult:
    status: RefreshRotationStatus
    session: RefreshSessionIdentity | None = None


def _refresh_session_ttl_seconds(settings: Settings) -> int:
    return max(1, settings.admin_refresh_token_ttl_days) * 24 * 60 * 60


def _refresh_family_key(family_id: str) -> str:
    return f"{_REFRESH_FAMILY_KEY_PREFIX}{family_id}"


def _active_session_state(jti: str) -> str:
    return jti


def _new_refresh_session(*, family_id: str | None = None) -> RefreshSessionIdentity:
    return RefreshSessionIdentity(
        family_id=family_id or secrets.token_urlsafe(32),
        jti=secrets.token_urlsafe(32),
    )


async def create_refresh_session(*, settings: Settings) -> RefreshSessionIdentity:
    client = await _require_redis_client(settings)
    ttl_seconds = _refresh_session_ttl_seconds(settings)
    session = _new_refresh_session()
    try:
        stored = await client.set(
            _refresh_family_key(session.family_id),
            _active_session_state(session.jti),
            ex=ttl_seconds,
            nx=True,
        )
    except Exception as exc:
        raise _auth_state_unavailable() from exc
    if not stored:
        raise AdminAuthStateError("Admin refresh session identity allocation failed")
    return session


async def revoke_logout_session(
    *,
    settings: Settings,
    access_revocation: AccessTokenRevocation | None,
    refresh_family_id: str | None,
) -> None:
    family_id = (refresh_family_id or "").strip()
    if access_revocation is None and not family_id:
        return
    try:
        client = await _require_redis_client(settings)
        eval_result = client.eval(
            _REVOKE_LOGOUT_SESSION_SCRIPT,
            2,
            access_revocation.key if access_revocation else _LOGOUT_ACCESS_PLACEHOLDER_KEY,
            _refresh_family_key(family_id) if family_id else _LOGOUT_REFRESH_PLACEHOLDER_KEY,
            "1" if access_revocation else "0",
            str(access_revocation.ttl_seconds if access_revocation else 1),
            "1" if family_id else "0",
            str(_refresh_session_ttl_seconds(settings)),
            _REVOKED_STATE,
        )
        if isinstance(eval_result, Awaitable):
            await eval_result
    except Exception as exc:
        logger.warning(
            "admin_logout_revocation_failed",
            reason="state_store_unavailable",
        )
        raise _auth_state_unavailable() from exc


async def rotate_refresh_session(
    *,
    settings: Settings,
    family_id: str,
    jti: str,
) -> RefreshRotationResult:
    if not family_id or not jti:
        return RefreshRotationResult(status=RefreshRotationStatus.MISSING)

    successor = _new_refresh_session(family_id=family_id)
    client = await _require_redis_client(settings)
    try:
        eval_result = client.eval(
            _ROTATE_REFRESH_SESSION_SCRIPT,
            1,
            _refresh_family_key(family_id),
            _active_session_state(jti),
            _active_session_state(successor.jti),
            _REVOKED_STATE,
            str(_refresh_session_ttl_seconds(settings)),
        )
        raw_result = await eval_result if isinstance(eval_result, Awaitable) else eval_result
        result_code = int(raw_result)
    except Exception as exc:
        raise _auth_state_unavailable() from exc

    if result_code == 1:
        return RefreshRotationResult(
            status=RefreshRotationStatus.ROTATED,
            session=successor,
        )
    if result_code == 2:
        return RefreshRotationResult(status=RefreshRotationStatus.MISSING)
    if result_code == 3:
        return RefreshRotationResult(status=RefreshRotationStatus.REVOKED)
    if result_code == 4:
        logger.warning(
            "admin_refresh_session_replay_detected",
            reason="predecessor_or_stale_session",
        )
        return RefreshRotationResult(status=RefreshRotationStatus.REPLAY)
    raise _auth_state_unavailable()


__all__ = [
    "RefreshRotationResult",
    "RefreshRotationStatus",
    "RefreshSessionIdentity",
    "create_refresh_session",
    "revoke_logout_session",
    "rotate_refresh_session",
]
