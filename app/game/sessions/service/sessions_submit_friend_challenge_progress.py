from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
    is_duel_playable_for_user,
    is_duel_playable_status,
)

from .sessions_submit_friend_challenge_resolution import (
    FriendDuelTiming,
    resolve_friend_challenge_winner,
    resolve_friend_duel_timing_if_needed,
)


async def record_friend_challenge_answer(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    is_creator: bool,
    has_opponent: bool,
    answered_round: int,
    is_correct: bool,
    now_utc: datetime,
) -> tuple[bool, FriendDuelTiming | None]:
    if not is_duel_playable_for_user(
        status=challenge.status,
        has_opponent=has_opponent,
        is_creator=is_creator,
    ):
        return False, None

    _apply_player_answer(
        challenge,
        is_creator=is_creator,
        answered_round=answered_round,
        is_correct=is_correct,
    )
    round_completed = _both_players_answered_round(
        challenge,
        has_opponent=has_opponent,
        answered_round=answered_round,
    ) and is_duel_playable_status(challenge.status)
    _advance_current_round(challenge)
    _mark_finished_players(challenge, now_utc=now_utc)

    result_timing = await _settle_friend_challenge_status(
        session,
        challenge=challenge,
        has_opponent=has_opponent,
        now_utc=now_utc,
    )
    return round_completed or challenge.status == DUEL_STATUS_COMPLETED, result_timing


def _apply_player_answer(
    challenge: FriendChallenge,
    *,
    is_creator: bool,
    answered_round: int,
    is_correct: bool,
) -> None:
    if is_creator and challenge.creator_answered_round < answered_round:
        if is_correct:
            challenge.creator_score += 1
        challenge.creator_answered_round = answered_round
    if not is_creator and challenge.opponent_answered_round < answered_round:
        if is_correct:
            challenge.opponent_score += 1
        challenge.opponent_answered_round = answered_round


def _both_players_answered_round(
    challenge: FriendChallenge,
    *,
    has_opponent: bool,
    answered_round: int,
) -> bool:
    return (
        has_opponent
        and challenge.creator_answered_round >= answered_round
        and challenge.opponent_answered_round >= answered_round
    )


def _advance_current_round(challenge: FriendChallenge) -> None:
    max_answered_round = max(
        challenge.creator_answered_round,
        challenge.opponent_answered_round,
    )
    challenge.current_round = min(challenge.total_rounds, max_answered_round + 1)


def _mark_finished_players(challenge: FriendChallenge, *, now_utc: datetime) -> None:
    if challenge.creator_answered_round >= challenge.total_rounds:
        challenge.creator_finished_at = challenge.creator_finished_at or now_utc
    if challenge.opponent_answered_round >= challenge.total_rounds:
        challenge.opponent_finished_at = challenge.opponent_finished_at or now_utc


async def _settle_friend_challenge_status(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    has_opponent: bool,
    now_utc: datetime,
) -> FriendDuelTiming | None:
    if challenge.creator_finished_at and challenge.opponent_finished_at:
        challenge.current_round = challenge.total_rounds
        challenge.status = DUEL_STATUS_COMPLETED
        challenge.completed_at = now_utc
        result_timing = await resolve_friend_duel_timing_if_needed(session, challenge=challenge)
        challenge.winner_user_id = resolve_friend_challenge_winner(
            challenge,
            timing=result_timing,
        )
        return result_timing
    if challenge.creator_finished_at:
        challenge.status = DUEL_STATUS_CREATOR_DONE
    elif challenge.opponent_finished_at:
        challenge.status = DUEL_STATUS_OPPONENT_DONE
    else:
        challenge.status = DUEL_STATUS_ACCEPTED if has_opponent else DUEL_STATUS_PENDING
    return None
