from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT
from app.game.sessions.types import FriendChallengeSnapshot

from .constants import FRIEND_CHALLENGE_TOTAL_ROUNDS
from .friend_challenges_create_analytics import emit_rematch_duel_created_events
from .friend_challenges_create_drafts import build_rematch_friend_challenge_draft
from .friend_challenges_create_rows import create_friend_challenge_from_draft
from .friend_challenges_create_standard import (
    create_friend_challenge as create_standard_friend_challenge,
)
from .friend_challenges_create_state import load_friend_challenge_rematch_context
from .friend_challenges_records import _build_friend_challenge_snapshot


async def create_friend_challenge(
    session: AsyncSession,
    *,
    creator_user_id: int,
    mode_code: str,
    now_utc: datetime,
    challenge_type: str = DUEL_TYPE_DIRECT,
    total_rounds: int = FRIEND_CHALLENGE_TOTAL_ROUNDS,
) -> FriendChallengeSnapshot:
    return await create_standard_friend_challenge(
        session,
        creator_user_id=creator_user_id,
        mode_code=mode_code,
        now_utc=now_utc,
        challenge_type=challenge_type,
        total_rounds=total_rounds,
    )


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
    rematch = await create_friend_challenge_from_draft(
        session,
        draft=draft,
        now_utc=now_utc,
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
