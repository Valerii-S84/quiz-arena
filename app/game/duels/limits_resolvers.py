from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_friend_create_access_type(
    session: AsyncSession,
    *,
    creator_user_id: int,
    now_utc: datetime,
    users_repo,
    entitlements_repo,
    friend_challenges_repo,
    resolve_access_type,
    free_limit_for_action,
    count_paid_ticket_uses,
    duel_access_free: str,
    duel_access_premium: str,
    duel_limit_action_friend_create: str,
    duel_ticket_product_code: str,
    purchases_repo,
) -> str:
    from app.game.sessions.errors import (
        FriendChallengeAccessError,
        FriendChallengePaymentRequiredError,
    )

    creator = await users_repo.get_by_id_for_update(session, creator_user_id)
    if creator is None:
        raise FriendChallengeAccessError
    premium_active = await entitlements_repo.has_active_premium(session, creator_user_id, now_utc)
    if premium_active:
        return duel_access_premium

    day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    free_used_today = (
        await friend_challenges_repo.count_by_creator_access_type_excluding_arena_revanche(
            session,
            creator_user_id=creator_user_id,
            access_type=duel_access_free,
            since=day_start,
        )
    )
    if free_used_today < free_limit_for_action(duel_limit_action_friend_create):
        return duel_access_free

    paid_ticket_uses = await count_paid_ticket_uses(session, user_id=creator_user_id)
    credited_tickets = await purchases_repo.count_credited_product(
        session,
        user_id=creator_user_id,
        product_code=duel_ticket_product_code,
    )
    decision = resolve_access_type(
        action=duel_limit_action_friend_create,
        premium_active=False,
        free_used_today=free_used_today,
        paid_ticket_uses=paid_ticket_uses,
        credited_tickets=credited_tickets,
    )
    if not decision.allowed or decision.access_type is None:
        raise FriendChallengePaymentRequiredError
    return decision.access_type


async def resolve_arena_access_type(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
    count_free_uses,
    access_error: type[Exception],
    payment_required_error: type[Exception],
    duel_limit_action: str,
    duel_access_free: str,
    duel_access_premium: str,
    ensure_user_exists,
    has_active_premium,
    berlin_day_start_utc,
    resolve_non_premium_access_type,
) -> str:
    await ensure_user_exists(session, user_id=user_id, access_error=access_error)
    premium_active = await has_active_premium(session, user_id, now_utc)
    if premium_active:
        return duel_access_premium
    free_used_today = await count_free_uses(
        session,
        user_id=user_id,
        access_type=duel_access_free,
        since=berlin_day_start_utc(now_utc),
    )
    return await resolve_non_premium_access_type(
        session,
        user_id=user_id,
        action=duel_limit_action,
        free_used_today=free_used_today,
        payment_required_error=payment_required_error,
    )


async def resolve_revanche_access_type(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
    analytics_repo,
    revanche_event_type: str,
    access_error: type[Exception],
    payment_required_error: type[Exception],
    duel_limit_action: str,
    duel_access_free: str,
    duel_access_premium: str,
    ensure_user_exists,
    has_active_premium,
    berlin_day_start_utc,
    resolve_non_premium_access_type,
) -> str:
    await ensure_user_exists(session, user_id=user_id, access_error=access_error)
    premium_active = await has_active_premium(session, user_id, now_utc)
    if premium_active:
        return duel_access_premium
    free_used_today = await analytics_repo.count_user_events_since_by_payload_value(
        session,
        event_type=revanche_event_type,
        user_id=user_id,
        since_utc=berlin_day_start_utc(now_utc),
        payload_key="access_type",
        payload_value=duel_access_free,
    )
    return await resolve_non_premium_access_type(
        session,
        user_id=user_id,
        action=duel_limit_action,
        free_used_today=free_used_today,
        payment_required_error=payment_required_error,
    )
