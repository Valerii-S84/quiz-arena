from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_SOURCE,
)
from app.game.sessions.types import SessionQuestionView, StartSessionResult

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
MODE_CODE = "QUICK_MIX_A1A2"


def question_ids() -> list[str]:
    return [f"arena-q-{number}" for number in range(1, 8)]


def start_result(question_id: str = "arena-q-1") -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=uuid4(),
            question_id=question_id,
            text="Question?",
            options=("A", "B", "C", "D"),
            mode_code=MODE_CODE,
            source=ARENA_SOURCE,
            question_number=1,
            total_questions=7,
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=False,
    )


def duel(*, duel_id: UUID | None = None, status: str = ARENA_DUEL_STATUS_DRAFT) -> ArenaDuel:
    return ArenaDuel(
        id=duel_id or uuid4(),
        creator_user_id=11,
        baseline_attempt_id=None,
        question_ids=question_ids(),
        mode_code=MODE_CODE,
        status=status,
        expires_at=NOW_UTC + timedelta(hours=1),
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
        source_friend_challenge_id=None,
    )


def active_duel(*, creator_user_id: int = 11) -> ArenaDuel:
    arena_duel = duel(status=ARENA_DUEL_STATUS_ACTIVE)
    arena_duel.creator_user_id = creator_user_id
    arena_duel.baseline_attempt_id = uuid4()
    return arena_duel


def challenger_attempt(*, duel_id: UUID, user_id: int = 22) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=user_id,
        role=ARENA_ATTEMPT_ROLE_CHALLENGER,
        score=None,
        time_ms=None,
        result=None,
        completed_at=None,
        created_at=NOW_UTC,
    )
