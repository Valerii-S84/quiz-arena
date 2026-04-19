from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

from .constants import FRIEND_CHALLENGE_TOTAL_ROUNDS
from .friend_challenges_analytics import (
    emit_rematch_duel_created_events,
    emit_standard_duel_created_events,
)
from .friend_challenges_create_drafts import (
    build_create_friend_challenge_draft,
    build_rematch_friend_challenge_draft,
)
from .friend_challenges_create_limits import resolve_friend_challenge_create_request
from .friend_challenges_create_state import load_friend_challenge_rematch_context
from .friend_challenges_internal import (
    _build_friend_challenge_snapshot,
    _create_friend_challenge_row,
)


async def create_friend_challenge(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    now_utc: datetime,
    challenge_type: str = DUEL_TYPE_DIRECT,
    total_rounds: int = FRIEND_CHALLENGE_TOTAL_ROUNDS,
) -> FriendChallengeSnapshot:
    request = await resolve_friend_challenge_create_request(
        session,
        creator_user_id=creator_user_id,
        challenge_type=challenge_type,
        total_rounds=total_rounds,
        now_utc=now_utc,
    )
    draft = await build_create_friend_challenge_draft(
        session,
        creator_user_id=creator_user_id,
        challenge_type=request.challenge_type,
        mode_code=mode_code,
        total_rounds=request.total_rounds,
        now_utc=now_utc,
    )
    challenge = await _create_friend_challenge_row(
        session,
        challenge_id=draft.challenge_id,
        creator_user_id=draft.creator_user_id,
        opponent_user_id=draft.opponent_user_id,
        challenge_type=draft.challenge_type,
        mode_code=draft.mode_code,
        access_type=draft.access_type,
        total_rounds=draft.total_rounds,
        now_utc=now_utc,
        question_ids=draft.question_ids,
        status=draft.status,
    )
    await emit_standard_duel_created_events(
        session,
        challenge=challenge,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
        creator_user_id=creator_user_id,
    )
    return _build_friend_challenge_snapshot(challenge)


async def create_friend_challenge_rematch(
    session: AsyncSession,
    *,
    initiator_user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    context = await load_friend_challenge_rematch_context(
        session,
        challenge_id=challenge_id,
        initiator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    draft = await build_rematch_friend_challenge_draft(
        session,
        challenge=context.challenge,
        initiator_user_id=initiator_user_id,
        opponent_user_id=context.opponent_user_id,
        now_utc=now_utc,
    )
    rematch = await _create_friend_challenge_row(
        session,
        challenge_id=draft.challenge_id,
        creator_user_id=draft.creator_user_id,
        opponent_user_id=draft.opponent_user_id,
        challenge_type=draft.challenge_type,
        mode_code=draft.mode_code,
        access_type=draft.access_type,
        total_rounds=draft.total_rounds,
        now_utc=now_utc,
        question_ids=draft.question_ids,
        series_id=draft.series_id,
        series_game_number=draft.series_game_number,
        series_best_of=draft.series_best_of,
        status=draft.status,
    )
    await emit_rematch_duel_created_events(
        session,
        rematch=rematch,
        source_challenge_id=challenge_id,
        opponent_user_id=context.opponent_user_id,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
        initiator_user_id=initiator_user_id,
    )
    return _build_friend_challenge_snapshot(rematch)
