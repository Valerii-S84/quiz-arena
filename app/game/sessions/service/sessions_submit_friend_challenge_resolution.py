from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.game.duels.constants import DUEL_QUESTION_COUNT
from app.game.friend_challenges.constants import DUEL_TYPE_DIRECT


@dataclass(frozen=True, slots=True)
class FriendDuelTiming:
    creator_time_ms: int
    opponent_time_ms: int


def resolve_friend_challenge_winner(
    challenge: FriendChallenge,
    *,
    timing: FriendDuelTiming | None,
) -> int | None:
    if challenge.creator_score > challenge.opponent_score:
        return int(challenge.creator_user_id)
    if (
        challenge.opponent_score > challenge.creator_score
        and challenge.opponent_user_id is not None
    ):
        return int(challenge.opponent_user_id)
    if timing is None:
        return None
    return _resolve_time_tie_break_winner(challenge=challenge, timing=timing)


async def resolve_friend_duel_timing_if_needed(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
) -> FriendDuelTiming | None:
    if not _uses_time_tie_break(challenge):
        return None
    opponent_user_id = challenge.opponent_user_id
    if opponent_user_id is None:
        return None
    creator_time_ms = await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
        session,
        friend_challenge_id=challenge.id,
        user_id=challenge.creator_user_id,
    )
    opponent_time_ms = await QuizSessionsRepo.sum_completed_duration_ms_for_friend_challenge_user(
        session,
        friend_challenge_id=challenge.id,
        user_id=opponent_user_id,
    )
    return FriendDuelTiming(
        creator_time_ms=creator_time_ms,
        opponent_time_ms=opponent_time_ms,
    )


def _uses_time_tie_break(challenge: FriendChallenge) -> bool:
    return (
        challenge.tournament_match_id is None
        and challenge.challenge_type == DUEL_TYPE_DIRECT
        and int(challenge.total_rounds) == DUEL_QUESTION_COUNT
        and challenge.opponent_user_id is not None
    )


def _resolve_time_tie_break_winner(
    *,
    challenge: FriendChallenge,
    timing: FriendDuelTiming,
) -> int | None:
    opponent_user_id = challenge.opponent_user_id
    if opponent_user_id is None:
        return None
    if timing.creator_time_ms < timing.opponent_time_ms:
        return int(challenge.creator_user_id)
    if timing.opponent_time_ms < timing.creator_time_ms:
        return int(opponent_user_id)
    return None
