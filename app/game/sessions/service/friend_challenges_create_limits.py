from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT, DUEL_TYPE_OPEN
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeLimitExceededError

from .constants import DUEL_MAX_ACTIVE_PER_USER, DUEL_MAX_NEW_PER_DAY
from .friend_challenges_question_plan import berlin_day_start_utc, resolve_duel_rounds


@dataclass(frozen=True, slots=True)
class FriendChallengeCreateRequest:
    challenge_type: str
    total_rounds: int


async def resolve_friend_challenge_create_request(
    session: AsyncSession,
    *,
    creator_user_id: int,
    challenge_type: str,
    total_rounds: int,
    now_utc: datetime,
) -> FriendChallengeCreateRequest:
    resolved_rounds = resolve_duel_rounds(total_rounds=total_rounds)
    if challenge_type not in {DUEL_TYPE_DIRECT, DUEL_TYPE_OPEN}:
        raise FriendChallengeAccessError
    live_duel_count = await FriendChallengesRepo.count_live_for_user(
        session,
        user_id=creator_user_id,
    )
    if live_duel_count >= DUEL_MAX_ACTIVE_PER_USER:
        raise FriendChallengeLimitExceededError
    if challenge_type == DUEL_TYPE_OPEN:
        open_count = await FriendChallengesRepo.count_live_open_by_creator(
            session,
            creator_user_id=creator_user_id,
        )
        if open_count > 0:
            raise FriendChallengeLimitExceededError
    created_today = await FriendChallengesRepo.count_created_since(
        session,
        creator_user_id=creator_user_id,
        created_after_utc=berlin_day_start_utc(now_utc=now_utc),
    )
    if created_today >= DUEL_MAX_NEW_PER_DAY:
        raise FriendChallengeLimitExceededError
    return FriendChallengeCreateRequest(
        challenge_type=challenge_type,
        total_rounds=resolved_rounds,
    )
