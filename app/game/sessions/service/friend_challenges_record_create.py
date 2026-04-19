from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
    DUEL_TYPE_DIRECT,
)

from .constants import DUEL_ACCEPTED_TTL_SECONDS, DUEL_PENDING_TTL_SECONDS


def _friend_challenge_expires_at(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=DUEL_PENDING_TTL_SECONDS)


def _friend_challenge_expires_at_accepted(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=DUEL_ACCEPTED_TTL_SECONDS)


def _friend_challenge_expires_at_for_status(
    *,
    status: str,
    now_utc: datetime,
) -> datetime:
    if status in {DUEL_STATUS_ACCEPTED, DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE}:
        return _friend_challenge_expires_at_accepted(now_utc=now_utc)
    return _friend_challenge_expires_at(now_utc=now_utc)


def _friend_challenge_series_fields(
    *,
    total_rounds: int,
    series_id: UUID | None,
    series_game_number: int,
    series_best_of: int,
) -> dict[str, object]:
    return {
        "total_rounds": max(1, total_rounds),
        "series_id": series_id,
        "series_game_number": max(1, int(series_game_number)),
        "series_best_of": max(1, int(series_best_of)),
    }


def _friend_challenge_progress_fields() -> dict[str, object]:
    return {
        "current_round": 1,
        "creator_score": 0,
        "opponent_score": 0,
        "creator_answered_round": 0,
        "opponent_answered_round": 0,
        "winner_user_id": None,
        "creator_finished_at": None,
        "opponent_finished_at": None,
        "creator_push_count": 0,
        "opponent_push_count": 0,
        "creator_proof_card_file_id": None,
        "opponent_proof_card_file_id": None,
        "expires_last_chance_notified_at": None,
        "completed_at": None,
    }


def _friend_challenge_timing_fields(
    *,
    status: str,
    now_utc: datetime,
) -> dict[str, object]:
    return {
        "expires_at": _friend_challenge_expires_at_for_status(
            status=status,
            now_utc=now_utc,
        ),
        "created_at": now_utc,
        "updated_at": now_utc,
    }


def _friend_challenge_row(
    *,
    challenge_id: UUID | None,
    creator_user_id: int,
    opponent_user_id: int | None,
    challenge_type: str,
    mode_code: str,
    access_type: str,
    total_rounds: int,
    now_utc: datetime,
    question_ids: list[str] | None,
    series_id: UUID | None,
    series_game_number: int,
    series_best_of: int,
    status: str,
) -> FriendChallenge:
    return FriendChallenge(
        id=challenge_id or uuid4(),
        invite_token=uuid4().hex,
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type=challenge_type,
        mode_code=mode_code,
        access_type=access_type,
        question_ids=question_ids,
        tournament_match_id=None,
        status=status,
        **_friend_challenge_series_fields(
            total_rounds=total_rounds,
            series_id=series_id,
            series_game_number=series_game_number,
            series_best_of=series_best_of,
        ),
        **_friend_challenge_progress_fields(),
        **_friend_challenge_timing_fields(
            status=status,
            now_utc=now_utc,
        ),
    )


async def _create_friend_challenge_row(
    session: AsyncSession,
    *,
    challenge_id: UUID | None = None,
    creator_user_id: int,
    opponent_user_id: int | None,
    challenge_type: str = DUEL_TYPE_DIRECT,
    mode_code: str,
    access_type: str,
    total_rounds: int,
    now_utc: datetime,
    question_ids: list[str] | None = None,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    status: str = DUEL_STATUS_PENDING,
) -> FriendChallenge:
    return await FriendChallengesRepo.create(
        session,
        challenge=_friend_challenge_row(
            challenge_id=challenge_id,
            creator_user_id=creator_user_id,
            opponent_user_id=opponent_user_id,
            challenge_type=challenge_type,
            mode_code=mode_code,
            access_type=access_type,
            total_rounds=total_rounds,
            now_utc=now_utc,
            question_ids=question_ids,
            series_id=series_id,
            series_game_number=series_game_number,
            series_best_of=series_best_of,
            status=status,
        ),
    )
