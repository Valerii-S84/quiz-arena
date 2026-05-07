from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_user_exists(
    session: AsyncSession,
    *,
    user_id: int,
    access_error: type[Exception],
    users_repo,
) -> None:
    user = await users_repo.get_by_id_for_update(session, user_id)
    if user is None:
        raise access_error


async def resolve_non_premium_access_type(
    session: AsyncSession,
    *,
    user_id: int,
    action: str,
    free_used_today: int,
    payment_required_error: type[Exception],
    count_paid_ticket_uses,
    purchases_repo,
    duel_ticket_product_code: str,
    resolve_access_type,
) -> str:
    paid_ticket_uses = await count_paid_ticket_uses(session, user_id=user_id)
    credited_tickets = await purchases_repo.count_credited_product(
        session,
        user_id=user_id,
        product_code=duel_ticket_product_code,
    )
    decision = resolve_access_type(
        action=action,
        premium_active=False,
        free_used_today=free_used_today,
        paid_ticket_uses=paid_ticket_uses,
        credited_tickets=credited_tickets,
    )
    if not decision.allowed or decision.access_type is None:
        raise payment_required_error
    return decision.access_type


async def count_paid_ticket_uses(
    session: AsyncSession,
    *,
    user_id: int,
    friend_challenges_repo,
    analytics_repo,
    arena_duels_repo,
    paid_access_type: str,
    revanche_event_type: str,
) -> int:
    friend_uses = (
        await friend_challenges_repo.count_by_creator_access_type_excluding_arena_revanche(
            session,
            creator_user_id=user_id,
            access_type=paid_access_type,
        )
    )
    arena_uses = await arena_duels_repo.count_paid_ticket_usage(session, user_id=user_id)
    revanche_uses = await analytics_repo.count_user_events_by_payload_value(
        session,
        event_type=revanche_event_type,
        user_id=user_id,
        payload_key="access_type",
        payload_value=paid_access_type,
    )
    return friend_uses + arena_uses + revanche_uses
