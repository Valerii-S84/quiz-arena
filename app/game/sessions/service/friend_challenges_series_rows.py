from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge

from .friend_challenges_records import _create_friend_challenge_row
from .friend_challenges_series_drafts import FriendChallengeSeriesDraft


async def create_series_friend_challenge_from_draft(
    session: AsyncSession,
    *,
    draft: FriendChallengeSeriesDraft,
    now_utc: datetime,
) -> FriendChallenge:
    return await _create_friend_challenge_row(
        session,
        creator_user_id=draft.creator_user_id,
        opponent_user_id=draft.opponent_user_id,
        challenge_type=draft.challenge_type,
        mode_code=draft.mode_code,
        access_type=draft.access_type,
        total_rounds=draft.total_rounds,
        now_utc=now_utc,
        series_id=draft.series_id,
        series_game_number=draft.series_game_number,
        series_best_of=draft.series_best_of,
        status=draft.status,
    )
