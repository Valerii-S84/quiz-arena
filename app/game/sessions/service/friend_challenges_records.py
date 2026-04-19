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
from app.game.sessions.types import FriendChallengeSnapshot

from .constants import DUEL_ACCEPTED_TTL_SECONDS, DUEL_PENDING_TTL_SECONDS


def _friend_challenge_expires_at(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=DUEL_PENDING_TTL_SECONDS)


def _friend_challenge_expires_at_accepted(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=DUEL_ACCEPTED_TTL_SECONDS)


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
    expires_at = (
        _friend_challenge_expires_at_accepted(now_utc=now_utc)
        if status in {DUEL_STATUS_ACCEPTED, DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE}
        else _friend_challenge_expires_at(now_utc=now_utc)
    )
    return await FriendChallengesRepo.create(
        session,
        challenge=FriendChallenge(
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
            current_round=1,
            total_rounds=max(1, total_rounds),
            series_id=series_id,
            series_game_number=max(1, int(series_game_number)),
            series_best_of=max(1, int(series_best_of)),
            creator_score=0,
            opponent_score=0,
            creator_answered_round=0,
            opponent_answered_round=0,
            winner_user_id=None,
            creator_finished_at=None,
            opponent_finished_at=None,
            creator_push_count=0,
            opponent_push_count=0,
            creator_proof_card_file_id=None,
            opponent_proof_card_file_id=None,
            expires_at=expires_at,
            expires_last_chance_notified_at=None,
            created_at=now_utc,
            updated_at=now_utc,
            completed_at=None,
        ),
    )


def _build_friend_challenge_snapshot(challenge: FriendChallenge) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=challenge.id,
        invite_token=challenge.invite_token,
        challenge_type=challenge.challenge_type,
        mode_code=challenge.mode_code,
        access_type=challenge.access_type,
        status=challenge.status,
        creator_user_id=challenge.creator_user_id,
        opponent_user_id=challenge.opponent_user_id,
        question_ids=tuple(challenge.question_ids or []),
        current_round=challenge.current_round,
        total_rounds=challenge.total_rounds,
        creator_finished_at=challenge.creator_finished_at,
        opponent_finished_at=challenge.opponent_finished_at,
        series_id=challenge.series_id,
        series_game_number=challenge.series_game_number,
        series_best_of=challenge.series_best_of,
        creator_score=challenge.creator_score,
        opponent_score=challenge.opponent_score,
        winner_user_id=challenge.winner_user_id,
        expires_at=challenge.expires_at,
        tournament_match_id=challenge.tournament_match_id,
    )
