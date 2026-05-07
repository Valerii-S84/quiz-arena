from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.entitlements_repo import EntitlementsRepo as _EntitlementsRepo
from app.db.repo.friend_challenges_repo import FriendChallengesRepo as _FriendChallengesRepo
from app.db.repo.purchases_repo import PurchasesRepo as _PurchasesRepo
from app.db.repo.users_repo import UsersRepo as _UsersRepo

from .limits_logic import (
    DUEL_ACCESS_FREE,
    DUEL_ACCESS_PAID_TICKET,
    DUEL_ACCESS_PREMIUM,
    DUEL_ACCESS_TYPES,
    DuelLimitDecision,
    assert_resolved_access_type,
    assert_start_gate,
    berlin_day_start_utc,
    free_limit_for_action,
    paywall_product_codes,
    paywall_products,
    resolve_access_type,
)
from .limits_service_api import count_paid_ticket_uses as _count_paid_ticket_uses_api
from .limits_service_api import ensure_user_exists as _ensure_user_exists_api
from .limits_service_api import (
    resolve_arena_accept_access_type as _resolve_arena_accept_access_type_api,
)
from .limits_service_api import (
    resolve_arena_create_access_type as _resolve_arena_create_access_type_api,
)
from .limits_service_api import (
    resolve_friend_create_access_type as _resolve_friend_create_access_type_api,
)
from .limits_service_api import (
    resolve_non_premium_access_type as _resolve_non_premium_access_type_api,
)
from .limits_service_api import resolve_revanche_access_type as _resolve_revanche_access_type_api

_berlin_day_start_utc = berlin_day_start_utc
UsersRepo = _UsersRepo
EntitlementsRepo = _EntitlementsRepo
FriendChallengesRepo = _FriendChallengesRepo
PurchasesRepo = _PurchasesRepo


class DuelLimitService:
    free_limit_for_action = staticmethod(free_limit_for_action)
    paywall_product_codes = staticmethod(paywall_product_codes)
    paywall_products = staticmethod(paywall_products)
    assert_start_gate = staticmethod(assert_start_gate)
    assert_resolved_access_type = staticmethod(assert_resolved_access_type)
    resolve_access_type = staticmethod(resolve_access_type)

    @staticmethod
    async def resolve_friend_create_access_type(
        session: AsyncSession,
        *,
        creator_user_id: int,
        now_utc: datetime,
    ) -> str:
        return await _resolve_friend_create_access_type_api(
            session,
            creator_user_id=creator_user_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def resolve_arena_create_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> str:
        return await _resolve_arena_create_access_type_api(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def resolve_arena_accept_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> str:
        return await _resolve_arena_accept_access_type_api(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def resolve_revanche_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        now_utc: datetime,
    ) -> str:
        return await _resolve_revanche_access_type_api(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def _resolve_non_premium_access_type(
        session: AsyncSession,
        *,
        user_id: int,
        action: str,
        free_used_today: int,
        payment_required_error: type[Exception],
    ) -> str:
        return await _resolve_non_premium_access_type_api(
            session,
            user_id=user_id,
            action=action,
            free_used_today=free_used_today,
            payment_required_error=payment_required_error,
        )

    @staticmethod
    async def _count_paid_ticket_uses(session: AsyncSession, *, user_id: int) -> int:
        return await _count_paid_ticket_uses_api(session, user_id=user_id)

    @staticmethod
    async def _ensure_user_exists(
        session: AsyncSession,
        *,
        user_id: int,
        access_error: type[Exception],
    ) -> None:
        await _ensure_user_exists_api(
            session,
            user_id=user_id,
            access_error=access_error,
        )


__all__ = [
    "DUEL_ACCESS_FREE",
    "DUEL_ACCESS_PAID_TICKET",
    "DUEL_ACCESS_PREMIUM",
    "DUEL_ACCESS_TYPES",
    "DuelLimitDecision",
    "DuelLimitService",
    "_berlin_day_start_utc",
]
