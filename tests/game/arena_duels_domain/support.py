from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_SOURCE,
)
from app.game.duels.limits import DUEL_ACCESS_FREE
from app.game.sessions.types import SessionQuestionView, StartSessionResult
from tests.type_helpers import AsyncSessionStub

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
        access_type=DUEL_ACCESS_FREE,
        status=status,
        expires_at=NOW_UTC + timedelta(hours=1),
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
        source_friend_challenge_id=None,
    )


def baseline_attempt(*, duel_id: UUID) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=11,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
        access_type=DUEL_ACCESS_FREE,
        score=None,
        time_ms=None,
        result=None,
        completed_at=None,
        created_at=NOW_UTC,
    )


def challenger_attempt(*, duel_id: UUID) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=22,
        role=ARENA_ATTEMPT_ROLE_CHALLENGER,
        access_type=DUEL_ACCESS_FREE,
        score=None,
        time_ms=None,
        result=None,
        completed_at=None,
        created_at=NOW_UTC,
    )


def completed_attempt(
    *,
    duel_id: UUID,
    user_id: int,
    score: int,
    time_ms: int,
    role: str = ARENA_ATTEMPT_ROLE_CHALLENGER,
) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=user_id,
        role=role,
        access_type=DUEL_ACCESS_FREE,
        score=score,
        time_ms=time_ms,
        result=ARENA_ATTEMPT_RESULT_WIN,
        completed_at=NOW_UTC,
        created_at=NOW_UTC,
    )


class EmptyRows:
    def all(self) -> list[object]:
        return []

    def one_or_none(self) -> None:
        return None


class OneRow:
    def __init__(self, row: tuple[int, int, int]) -> None:
        self._row = row

    def one(self) -> tuple[int, int, int]:
        return self._row


class RecordingSession(AsyncSessionStub):
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return EmptyRows()


class ScalarRows:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar_one(self) -> int:
        return self._value


class ScalarRecordingSession(AsyncSessionStub):
    def __init__(self, *, values: tuple[int, ...]) -> None:
        self.statements: list[Any] = []
        self._values = iter(values)

    async def execute(self, statement):
        self.statements.append(statement)
        return ScalarRows(next(self._values))


class RowcountRecordingSession(AsyncSessionStub):
    def __init__(self, *, rowcount: int) -> None:
        self.statement = None
        self._rowcount = rowcount

    async def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(rowcount=self._rowcount)


class OneRowRecordingSession(AsyncSessionStub):
    def __init__(self, row: tuple[int, int, int]) -> None:
        self.statement = None
        self._row = row

    async def execute(self, statement):
        self.statement = statement
        return OneRow(self._row)
