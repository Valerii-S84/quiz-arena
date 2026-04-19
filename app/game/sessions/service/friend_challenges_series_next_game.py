from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT
from app.game.sessions.types import FriendChallengeSnapshot

from .friend_challenges_records import _build_friend_challenge_snapshot
from .friend_challenges_series_analytics import emit_series_next_game_created_events
from .friend_challenges_series_drafts import build_series_next_game_friend_challenge_draft
from .friend_challenges_series_rows import create_series_friend_challenge_from_draft
from .friend_challenges_series_state import load_friend_challenge_series_context


async def create_friend_challenge_series_next_game(
    session: AsyncSession,
    *,
    initiator_user_id: int,
    challenge_id: UUID,
    now_utc: datetime,
) -> FriendChallengeSnapshot:
    context = await load_friend_challenge_series_context(
        session,
        challenge_id=challenge_id,
        initiator_user_id=initiator_user_id,
        now_utc=now_utc,
    )
    draft = await build_series_next_game_friend_challenge_draft(
        session,
        challenge=context.challenge,
        initiator_user_id=initiator_user_id,
        opponent_user_id=context.opponent_user_id,
        now_utc=now_utc,
    )
    duel = await create_series_friend_challenge_from_draft(
        session,
        draft=draft,
        now_utc=now_utc,
    )
    await emit_series_next_game_created_events(
        session,
        duel=duel,
        source_challenge_id=challenge_id,
        opponent_user_id=context.opponent_user_id,
        happened_at=now_utc,
        source=EVENT_SOURCE_BOT,
        initiator_user_id=initiator_user_id,
    )
    return _build_friend_challenge_snapshot(duel)
