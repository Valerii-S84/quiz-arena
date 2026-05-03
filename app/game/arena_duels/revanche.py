from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import BERLIN_TIMEZONE, EVENT_SOURCE_BOT
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels.constants import ARENA_REVANCHE_SENT_EVENT
from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelNotFoundError
from app.game.arena_duels.revanche_friend_challenge import (
    build_arena_revanche_payload,
    create_revanche_friend_challenge,
    ensure_source_attempt_can_receive_revanche,
)
from app.game.arena_duels.revanche_types import ArenaRevancheContext, ArenaRevancheRequest
from app.game.duels.limits import DuelLimitService


async def load_arena_revanche_context(
    session: AsyncSession,
    *,
    sender_user_id: int,
    source_attempt_id: UUID,
) -> ArenaRevancheContext:
    context = await ArenaDuelsRepo.get_attempt_duel_for_update(
        session,
        attempt_id=source_attempt_id,
    )
    if context is None:
        raise ArenaDuelNotFoundError

    source_attempt = context.attempt
    ensure_source_attempt_can_receive_revanche(
        sender_user_id=sender_user_id,
        receiver_user_id=source_attempt.user_id,
        source_attempt_ready=(
            source_attempt.completed_at is not None
            and source_attempt.score is not None
            and source_attempt.time_ms is not None
        ),
    )
    has_sender_attempt = await ArenaDuelsRepo.has_completed_attempt_for_user(
        session,
        duel_id=context.duel.id,
        user_id=sender_user_id,
    )
    if not has_sender_attempt:
        raise ArenaDuelAccessError

    return ArenaRevancheContext(
        arena_duel_id=context.duel.id,
        source_attempt_id=source_attempt.id,
        sender_user_id=sender_user_id,
        receiver_user_id=source_attempt.user_id,
        mode_code=context.duel.mode_code,
    )


async def prepare_arena_revanche_request(
    session: AsyncSession,
    *,
    sender_user_id: int,
    source_attempt_id: UUID,
    now_utc: datetime,
) -> ArenaRevancheRequest:
    context = await load_arena_revanche_context(
        session,
        sender_user_id=sender_user_id,
        source_attempt_id=source_attempt_id,
    )
    payload = build_arena_revanche_payload(context=context)
    await AnalyticsRepo.lock_arena_revanche_event_key(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        user_id=sender_user_id,
        payload=payload,
    )
    already_sent = await AnalyticsRepo.has_arena_revanche_event(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        user_id=sender_user_id,
        payload=payload,
    )
    if already_sent:
        return ArenaRevancheRequest(context=context, challenge=None, already_sent=True)

    access_type = await DuelLimitService.resolve_revanche_access_type(
        session,
        user_id=sender_user_id,
        now_utc=now_utc,
    )
    challenge = await create_revanche_friend_challenge(
        session,
        context=context,
        access_type=access_type,
        now_utc=now_utc,
    )
    return ArenaRevancheRequest(context=context, challenge=challenge)


async def record_arena_revanche_sent(
    session: AsyncSession,
    *,
    request: ArenaRevancheRequest,
    happened_at: datetime,
    source: str = EVENT_SOURCE_BOT,
) -> bool:
    payload = build_arena_revanche_payload(
        context=request.context,
        challenge_id=None if request.challenge is None else request.challenge.challenge_id,
    )
    return await AnalyticsRepo.create_arena_revanche_event_once(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        source=source,
        user_id=request.context.sender_user_id,
        local_date_berlin=happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date(),
        payload=payload,
        happened_at=happened_at,
    )
