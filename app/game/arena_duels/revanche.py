from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import BERLIN_TIMEZONE, EVENT_SOURCE_BOT
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.game.arena_duels.constants import ARENA_REVANCHE_REQUESTED_EVENT, ARENA_REVANCHE_SENT_EVENT
from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelNotFoundError
from app.game.arena_duels.revanche_friend_challenge import (
    build_arena_revanche_payload,
    create_revanche_friend_challenge,
    delete_revanche_friend_challenge,
    ensure_source_attempt_can_receive_revanche,
    load_revanche_friend_challenge,
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
    await AnalyticsRepo.lock_arena_revanche_sender_quota(session, user_id=sender_user_id)
    await AnalyticsRepo.lock_arena_revanche_event_key(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        user_id=sender_user_id,
        payload=payload,
    )
    sent = await AnalyticsRepo.has_arena_revanche_event(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        user_id=sender_user_id,
        payload=payload,
    )
    if sent:
        return ArenaRevancheRequest(context=context, challenge=None, already_sent=True)

    pending_payload = await AnalyticsRepo.get_arena_revanche_event_payload(
        session,
        event_type=ARENA_REVANCHE_REQUESTED_EVENT,
        user_id=sender_user_id,
        payload=payload,
    )
    if pending_payload is not None:
        return ArenaRevancheRequest(
            context=context,
            challenge=await load_revanche_friend_challenge(
                session,
                challenge_id=UUID(str(pending_payload["challenge_id"])),
                context=context,
            ),
        )

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
    request = ArenaRevancheRequest(context=context, challenge=challenge)
    await record_arena_revanche_requested(session, request=request, happened_at=now_utc)
    return request


async def record_arena_revanche_requested(
    session: AsyncSession,
    *,
    request: ArenaRevancheRequest,
    happened_at: datetime,
    source: str = EVENT_SOURCE_BOT,
) -> bool:
    return await _record_arena_revanche_event(
        session,
        event_type=ARENA_REVANCHE_REQUESTED_EVENT,
        request=request,
        happened_at=happened_at,
        source=source,
    )


async def record_arena_revanche_sent(
    session: AsyncSession,
    *,
    request: ArenaRevancheRequest,
    happened_at: datetime,
    source: str = EVENT_SOURCE_BOT,
) -> bool:
    return await _record_arena_revanche_event(
        session,
        event_type=ARENA_REVANCHE_SENT_EVENT,
        request=request,
        happened_at=happened_at,
        source=source,
    )


async def cleanup_arena_revanche_request(
    session: AsyncSession,
    *,
    request: ArenaRevancheRequest,
) -> None:
    if request.challenge is not None:
        await delete_revanche_friend_challenge(
            session,
            challenge_id=request.challenge.challenge_id,
            context=request.context,
        )
    payload = build_arena_revanche_payload(context=request.context)
    await AnalyticsRepo.delete_arena_revanche_events(
        session,
        event_types=(ARENA_REVANCHE_REQUESTED_EVENT, ARENA_REVANCHE_SENT_EVENT),
        user_id=request.context.sender_user_id,
        payload=payload,
    )


async def _record_arena_revanche_event(
    session: AsyncSession,
    *,
    event_type: str,
    request: ArenaRevancheRequest,
    happened_at: datetime,
    source: str,
) -> bool:
    payload = build_arena_revanche_payload(
        context=request.context,
        challenge_id=None if request.challenge is None else request.challenge.challenge_id,
    )
    return await AnalyticsRepo.create_arena_revanche_event_once(
        session,
        event_type=event_type,
        source=source,
        user_id=request.context.sender_user_id,
        local_date_berlin=happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date(),
        payload=payload,
        happened_at=happened_at,
    )
