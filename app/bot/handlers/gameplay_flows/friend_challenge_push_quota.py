from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.sessions.service.constants import DUEL_MAX_PUSH_PER_USER


async def reserve_duel_push_slot(
    *,
    session_local,
    challenge_id: UUID,
    target_user_id: int,
    now_utc: datetime,
) -> bool:
    async with session_local.begin() as session:
        challenge_row = await FriendChallengesRepo.get_by_id_for_update(
            session,
            challenge_id,
        )
        if challenge_row is None:
            return False
        if challenge_row.creator_user_id == target_user_id:
            if challenge_row.creator_push_count >= DUEL_MAX_PUSH_PER_USER:
                return False
            challenge_row.creator_push_count += 1
            challenge_row.updated_at = now_utc
            return True
        if challenge_row.opponent_user_id == target_user_id:
            if challenge_row.opponent_push_count >= DUEL_MAX_PUSH_PER_USER:
                return False
            challenge_row.opponent_push_count += 1
            challenge_row.updated_at = now_utc
            return True
        return False
