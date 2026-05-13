from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.game.arena_duels.analytics import ARENA_EVENT_FRIEND_DUEL_STARTED
from app.game.sessions.types import FriendChallengeRoundStartResult

from .friend_challenges_internal import _build_friend_challenge_snapshot
from .friend_challenges_rounds_start import (
    build_existing_friend_challenge_round_start,
    start_new_friend_challenge_round_session,
)


async def build_friend_challenge_round_start_result(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    next_round: int,
    idempotency_key: str,
    now_utc: datetime,
    header_mode_label_override: str | None,
) -> FriendChallengeRoundStartResult:
    replay_result = await _existing_round_result(
        session,
        challenge=challenge,
        user_id=user_id,
        next_round=next_round,
        header_mode_label_override=header_mode_label_override,
    )
    if replay_result is not None:
        return replay_result
    return await _start_new_round_result(
        session,
        challenge=challenge,
        user_id=user_id,
        next_round=next_round,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
        header_mode_label_override=header_mode_label_override,
    )


async def _existing_round_result(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    next_round: int,
    header_mode_label_override: str | None,
) -> FriendChallengeRoundStartResult | None:
    start_result = await build_existing_friend_challenge_round_start(
        session,
        challenge=challenge,
        user_id=user_id,
        next_round=next_round,
        header_mode_label_override=header_mode_label_override,
    )
    if start_result is None:
        return None
    return FriendChallengeRoundStartResult(
        snapshot=_build_friend_challenge_snapshot(challenge),
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )


async def _start_new_round_result(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    next_round: int,
    idempotency_key: str,
    now_utc: datetime,
    header_mode_label_override: str | None,
) -> FriendChallengeRoundStartResult:
    start_result = await start_new_friend_challenge_round_session(
        session,
        challenge=challenge,
        user_id=user_id,
        next_round=next_round,
        idempotency_key=idempotency_key,
        now_utc=now_utc,
        header_mode_label_override=header_mode_label_override,
    )
    await _emit_friend_duel_started_event(
        session,
        user_id=user_id,
        challenge_id=challenge.id,
        round_number=next_round,
        total_rounds=challenge.total_rounds,
        happened_at=now_utc,
    )
    return FriendChallengeRoundStartResult(
        snapshot=_build_friend_challenge_snapshot(challenge),
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )


async def _emit_friend_duel_started_event(
    session: AsyncSession,
    *,
    user_id: int,
    challenge_id,
    round_number: int,
    total_rounds: int,
    happened_at: datetime,
) -> None:
    if not callable(getattr(session, "add", None)):
        return
    await emit_analytics_event(
        session,
        event_type=ARENA_EVENT_FRIEND_DUEL_STARTED,
        source=EVENT_SOURCE_BOT,
        happened_at=happened_at,
        user_id=user_id,
        payload={
            "challenge_id": str(challenge_id),
            "round": round_number,
            "total_rounds": total_rounds,
        },
    )
