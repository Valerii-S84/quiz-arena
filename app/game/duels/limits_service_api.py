from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.game.duels.constants import (
    DUEL_LIMIT_ACTION_ARENA_ACCEPT,
    DUEL_LIMIT_ACTION_ARENA_CREATE,
    DUEL_LIMIT_ACTION_FRIEND_CREATE,
    DUEL_LIMIT_ACTION_REVANCHE,
    DUEL_TICKET_PRODUCT_CODE,
)

from .limits_logic import DUEL_ACCESS_FREE, DUEL_ACCESS_PAID_TICKET, DUEL_ACCESS_PREMIUM
from .limits_resolvers import resolve_arena_access_type as _resolve_arena_access_type
from .limits_resolvers import (
    resolve_friend_create_access_type as _resolve_friend_create_access_type,
)
from .limits_resolvers import resolve_revanche_access_type as _resolve_revanche_access_type
from .limits_runtime import count_paid_ticket_uses as _count_paid_ticket_uses_impl
from .limits_runtime import ensure_user_exists as _ensure_user_exists_impl
from .limits_runtime import resolve_non_premium_access_type as _resolve_non_premium_access_type_impl


async def resolve_friend_create_access_type(
    session: AsyncSession,
    *,
    creator_user_id: int,
    now_utc: datetime,
) -> str:
    from app.game.duels import limits as limits_module

    return await _resolve_friend_create_access_type(
        session,
        creator_user_id=creator_user_id,
        now_utc=now_utc,
        berlin_day_start_utc=limits_module._berlin_day_start_utc,
        users_repo=limits_module.UsersRepo,
        entitlements_repo=limits_module.EntitlementsRepo,
        friend_challenges_repo=limits_module.FriendChallengesRepo,
        resolve_access_type=limits_module.DuelLimitService.resolve_access_type,
        free_limit_for_action=limits_module.DuelLimitService.free_limit_for_action,
        count_paid_ticket_uses=limits_module.DuelLimitService._count_paid_ticket_uses,
        duel_access_free=DUEL_ACCESS_FREE,
        duel_access_premium=DUEL_ACCESS_PREMIUM,
        duel_limit_action_friend_create=DUEL_LIMIT_ACTION_FRIEND_CREATE,
        duel_ticket_product_code=DUEL_TICKET_PRODUCT_CODE,
        purchases_repo=limits_module.PurchasesRepo,
    )


async def resolve_arena_create_access_type(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> str:
    from app.db.repo.arena_duels_repo import ArenaDuelsRepo
    from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelPaymentRequiredError
    from app.game.duels import limits as limits_module

    async def _count_creator_free_uses(
        session: AsyncSession,
        *,
        user_id: int,
        access_type: str,
        since: datetime | None = None,
    ) -> int:
        return await ArenaDuelsRepo.count_creator_duels_by_access_type(
            session,
            creator_user_id=user_id,
            access_type=access_type,
            since=since,
        )

    return await _resolve_arena_access_type(
        session,
        user_id=user_id,
        now_utc=now_utc,
        count_free_uses=_count_creator_free_uses,
        access_error=ArenaDuelAccessError,
        payment_required_error=ArenaDuelPaymentRequiredError,
        duel_limit_action=DUEL_LIMIT_ACTION_ARENA_CREATE,
        duel_access_free=DUEL_ACCESS_FREE,
        duel_access_premium=DUEL_ACCESS_PREMIUM,
        ensure_user_exists=limits_module.DuelLimitService._ensure_user_exists,
        has_active_premium=limits_module.EntitlementsRepo.has_active_premium,
        berlin_day_start_utc=limits_module._berlin_day_start_utc,
        resolve_non_premium_access_type=limits_module.DuelLimitService._resolve_non_premium_access_type,
    )


async def resolve_arena_accept_access_type(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> str:
    from app.db.repo.arena_duels_repo import ArenaDuelsRepo
    from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelPaymentRequiredError
    from app.game.duels import limits as limits_module

    return await _resolve_arena_access_type(
        session,
        user_id=user_id,
        now_utc=now_utc,
        count_free_uses=ArenaDuelsRepo.count_challenger_attempts_by_access_type,
        access_error=ArenaDuelAccessError,
        payment_required_error=ArenaDuelPaymentRequiredError,
        duel_limit_action=DUEL_LIMIT_ACTION_ARENA_ACCEPT,
        duel_access_free=DUEL_ACCESS_FREE,
        duel_access_premium=DUEL_ACCESS_PREMIUM,
        ensure_user_exists=limits_module.DuelLimitService._ensure_user_exists,
        has_active_premium=limits_module.EntitlementsRepo.has_active_premium,
        berlin_day_start_utc=limits_module._berlin_day_start_utc,
        resolve_non_premium_access_type=limits_module.DuelLimitService._resolve_non_premium_access_type,
    )


async def resolve_revanche_access_type(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> str:
    from app.db.repo.analytics_repo import AnalyticsRepo
    from app.game.arena_duels.constants import ARENA_REVANCHE_SENT_EVENT
    from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelPaymentRequiredError
    from app.game.duels import limits as limits_module

    return await _resolve_revanche_access_type(
        session,
        user_id=user_id,
        now_utc=now_utc,
        analytics_repo=AnalyticsRepo,
        revanche_event_type=ARENA_REVANCHE_SENT_EVENT,
        access_error=ArenaDuelAccessError,
        payment_required_error=ArenaDuelPaymentRequiredError,
        duel_limit_action=DUEL_LIMIT_ACTION_REVANCHE,
        duel_access_free=DUEL_ACCESS_FREE,
        duel_access_premium=DUEL_ACCESS_PREMIUM,
        ensure_user_exists=limits_module.DuelLimitService._ensure_user_exists,
        has_active_premium=limits_module.EntitlementsRepo.has_active_premium,
        berlin_day_start_utc=limits_module._berlin_day_start_utc,
        resolve_non_premium_access_type=limits_module.DuelLimitService._resolve_non_premium_access_type,
    )


async def resolve_non_premium_access_type(
    session: AsyncSession,
    *,
    user_id: int,
    action: str,
    free_used_today: int,
    payment_required_error: type[Exception],
) -> str:
    from app.game.duels import limits as limits_module

    return await _resolve_non_premium_access_type_impl(
        session,
        user_id=user_id,
        action=action,
        free_used_today=free_used_today,
        payment_required_error=payment_required_error,
        count_paid_ticket_uses=limits_module.DuelLimitService._count_paid_ticket_uses,
        purchases_repo=limits_module.PurchasesRepo,
        duel_ticket_product_code=DUEL_TICKET_PRODUCT_CODE,
        resolve_access_type=limits_module.DuelLimitService.resolve_access_type,
    )


async def count_paid_ticket_uses(session: AsyncSession, *, user_id: int) -> int:
    from app.db.repo.analytics_repo import AnalyticsRepo
    from app.db.repo.arena_duels_repo import ArenaDuelsRepo
    from app.game.arena_duels.constants import ARENA_REVANCHE_SENT_EVENT
    from app.game.duels import limits as limits_module

    return await _count_paid_ticket_uses_impl(
        session,
        user_id=user_id,
        friend_challenges_repo=limits_module.FriendChallengesRepo,
        analytics_repo=AnalyticsRepo,
        arena_duels_repo=ArenaDuelsRepo,
        paid_access_type=DUEL_ACCESS_PAID_TICKET,
        revanche_event_type=ARENA_REVANCHE_SENT_EVENT,
    )


async def ensure_user_exists(
    session: AsyncSession,
    *,
    user_id: int,
    access_error: type[Exception],
) -> None:
    from app.game.duels import limits as limits_module

    await _ensure_user_exists_impl(
        session,
        user_id=user_id,
        access_error=access_error,
        users_repo=limits_module.UsersRepo,
    )
