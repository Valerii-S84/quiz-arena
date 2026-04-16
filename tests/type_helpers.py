from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Generic, Mapping, TypeVar, cast
from uuid import uuid4

from fastapi import Request
from starlette.types import Message, Scope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSessionBase

    from app.core.config import Settings
else:
    Settings = Any

    class _AsyncSessionBase:
        pass


_T = TypeVar("_T")
_VALID_PROMO_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"


class AsyncSessionStub(_AsyncSessionBase):
    pass


class AsyncBeginContext(Generic[_T]):
    def __init__(self, value: _T) -> None:
        self._value = value

    async def __aenter__(self) -> _T:
        return self._value

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class ScalarResult(Generic[_T]):
    def __init__(self, value: _T) -> None:
        self._value = value

    def scalar_one(self) -> _T:
        return self._value

    def scalar_one_or_none(self) -> _T:
        return self._value


class RowsResult(Generic[_T]):
    def __init__(self, rows: list[_T]) -> None:
        self._rows = rows

    def all(self) -> list[_T]:
        return list(self._rows)


class ScalarsResult(Generic[_T]):
    def __init__(self, rows: list[_T]) -> None:
        self._rows = rows

    def scalars(self) -> ScalarsResult[_T]:
        return self

    def all(self) -> list[_T]:
        return list(self._rows)


def as_any_dict(payload: object) -> dict[str, Any]:
    return cast(dict[str, Any], payload)


def build_settings(**overrides: object) -> Settings:
    from app.core.config import Settings as SettingsModel

    payload: dict[str, object] = {
        "app_env": "test",
        "admin_frontend_origin": "http://localhost:3000",
        "admin_email": "admin@example.com",
        "admin_password_hash": "",
        "admin_password_plain": "secret123",
        "admin_jwt_secret": "jwt-secret",
        "admin_refresh_secret": "refresh-secret",
        "admin_2fa_required": True,
        "admin_totp_secret": "",
        "admin_totp_issuer": "Quiz Arena Admin",
        "admin_access_token_ttl_minutes": 15,
        "admin_refresh_token_ttl_days": 7,
        "admin_role": "admin",
        "admin_login_rate_limit_attempts": 3,
        "admin_login_rate_limit_window_minutes": 5,
        "telegram_bot_token": "test-token",
        "telegram_webhook_secret": "secret-token",
        "bonus_channel_id": "",
        "bonus_check_bot_token": "",
        "internal_api_token": "internal-token",
        "internal_api_allowlist": "127.0.0.1/32,::1/128",
        "internal_api_trusted_proxies": "127.0.0.1/32,::1/128",
        "promo_secret_pepper": "pepper",
        "promo_encryption_key": _VALID_PROMO_ENCRYPTION_KEY,
        "database_url": "postgresql+asyncpg://quiz:quiz@localhost:5432/quiz_arena_test",
        "redis_url": "redis://localhost:6379/15",
        "celery_broker_url": "redis://localhost:6379/15",
        "celery_result_backend": "redis://localhost:6379/15",
    }
    payload.update(overrides)
    return SettingsModel.model_construct(_fields_set=None, **payload)


def build_promo_code(**overrides: object):
    from app.db.models.promo_codes import PromoCode

    now_utc = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "id": 21,
        "code_hash": "promo-hash",
        "code_prefix": "PROMO",
        "code_encrypted": None,
        "campaign_name": "Test promo",
        "promo_type": "PERCENT_DISCOUNT",
        "grant_premium_days": None,
        "discount_percent": 40,
        "discount_type": "PERCENT",
        "discount_value": None,
        "applicable_products": None,
        "target_scope": "ANY",
        "status": "ACTIVE",
        "valid_from": now_utc - timedelta(days=1),
        "valid_until": now_utc + timedelta(days=1),
        "max_total_uses": 10,
        "used_total": 0,
        "max_uses_per_user": 1,
        "new_users_only": False,
        "first_purchase_only": False,
        "created_by": "tests",
        "created_at": now_utc,
        "updated_at": now_utc,
    }
    payload.update(overrides)
    return PromoCode(**payload)


def build_friend_challenge(**overrides: object):
    from app.db.models.friend_challenges import FriendChallenge

    now_utc = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "id": uuid4(),
        "invite_token": "invite-token",
        "creator_user_id": 10,
        "opponent_user_id": 22,
        "challenge_type": "DIRECT",
        "mode_code": "DAILY_CUP",
        "access_type": "FREE",
        "question_ids": None,
        "tournament_match_id": None,
        "status": "ACCEPTED",
        "current_round": 1,
        "total_rounds": 1,
        "series_id": None,
        "series_game_number": 1,
        "series_best_of": 1,
        "creator_score": 0,
        "opponent_score": 0,
        "creator_answered_round": 0,
        "opponent_answered_round": 0,
        "winner_user_id": None,
        "creator_finished_at": None,
        "opponent_finished_at": None,
        "creator_push_count": 0,
        "opponent_push_count": 0,
        "creator_proof_card_file_id": None,
        "opponent_proof_card_file_id": None,
        "expires_at": now_utc + timedelta(hours=6),
        "expires_last_chance_notified_at": None,
        "created_at": now_utc,
        "updated_at": now_utc,
        "completed_at": None,
    }
    payload.update(overrides)
    return FriendChallenge(**payload)


def build_promo_redemption(**overrides: object):
    from app.db.models.promo_redemptions import PromoRedemption

    now_utc = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "id": uuid4(),
        "promo_code_id": 21,
        "user_id": 7,
        "status": "APPLIED",
        "reject_reason": None,
        "reserved_until": None,
        "applied_purchase_id": None,
        "grant_entitlement_id": None,
        "idempotency_key": "promo:redemption:test",
        "validation_snapshot": {},
        "created_at": now_utc,
        "applied_at": None,
        "updated_at": now_utc,
    }
    payload.update(overrides)
    return PromoRedemption(**payload)


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def build_request(
    *,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    client_host: str | None = "127.0.0.1",
) -> Request:
    header_pairs = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        header_pairs.append((b"cookie", cookie_header.encode("latin-1")))

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": header_pairs,
        "client": None if client_host is None else (client_host, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope, receive=_empty_receive)
