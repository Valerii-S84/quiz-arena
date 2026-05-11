from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.models.friend_challenges import FriendChallenge
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    arena_duel_expires_at,
)
from app.game.arena_duels.errors import ArenaDuelAccessError
from app.game.arena_duels.types import ArenaDuelSnapshot
from app.game.duels.constants import DUEL_QUESTION_COUNT


def build_arena_publish_duel(
    *,
    challenge: FriendChallenge,
    question_ids: tuple[str, ...],
    access_type: str,
    now_utc: datetime,
) -> ArenaDuel:
    return ArenaDuel(
        id=uuid4(),
        creator_user_id=challenge.creator_user_id,
        baseline_attempt_id=None,
        question_ids=list(question_ids),
        mode_code=challenge.mode_code,
        access_type=access_type,
        status=ARENA_DUEL_STATUS_ACTIVE,
        expires_at=arena_duel_expires_at(now_utc=now_utc),
        created_at=now_utc,
        updated_at=now_utc,
        source_friend_challenge_id=challenge.id,
    )


def build_arena_publish_baseline_attempt(
    *,
    duel: ArenaDuel,
    challenge: FriendChallenge,
    access_type: str,
    baseline_time_ms: int,
    now_utc: datetime,
) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel.id,
        user_id=challenge.creator_user_id,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
        access_type=access_type,
        score=int(challenge.creator_score),
        time_ms=baseline_time_ms,
        result=ARENA_ATTEMPT_RESULT_BASELINE,
        completed_at=challenge.creator_finished_at,
        created_at=now_utc,
    )


def validate_arena_publish_question_ids(question_ids: object) -> tuple[str, ...]:
    if not isinstance(question_ids, list):
        raise ArenaDuelAccessError
    validated = tuple(question_id for question_id in question_ids if isinstance(question_id, str))
    if len(validated) != DUEL_QUESTION_COUNT or any(not question_id for question_id in validated):
        raise ArenaDuelAccessError
    return validated


def build_arena_duel_snapshot(
    *,
    duel: ArenaDuel,
    baseline_attempt: ArenaAttempt,
) -> ArenaDuelSnapshot:
    return ArenaDuelSnapshot(
        duel_id=duel.id,
        creator_user_id=duel.creator_user_id,
        mode_code=duel.mode_code,
        status=duel.status,
        question_ids=validate_arena_publish_question_ids(duel.question_ids),
        baseline_attempt_id=baseline_attempt.id,
        baseline_score=baseline_attempt.score,
        baseline_time_ms=baseline_attempt.time_ms,
        expires_at=duel.expires_at,
        created_at=duel.created_at,
        updated_at=duel.updated_at,
    )
