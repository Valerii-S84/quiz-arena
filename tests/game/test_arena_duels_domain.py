from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import (
    ArenaActiveDuelRow,
    ArenaAttemptCompletionSummary,
    ArenaAttemptDuelContext,
    ArenaDuelsRepo,
)
from app.game.arena_duels import service as arena_service
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_ATTEMPT_ROLE_CHALLENGER,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_DRAFT,
    ARENA_SOURCE,
)
from app.game.arena_duels.errors import ArenaDuelIncompleteError
from app.game.sessions.errors import DuelLimitRequiredError
from app.game.sessions.types import SessionQuestionView, StartSessionResult
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
MODE_CODE = "QUICK_MIX_A1A2"


def _question_ids() -> list[str]:
    return [f"arena-q-{number}" for number in range(1, 8)]


def _start_result(question_id: str = "arena-q-1") -> StartSessionResult:
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


def _duel(*, duel_id: UUID | None = None, status: str = ARENA_DUEL_STATUS_DRAFT) -> ArenaDuel:
    return ArenaDuel(
        id=duel_id or uuid4(),
        creator_user_id=11,
        baseline_attempt_id=None,
        question_ids=_question_ids(),
        mode_code=MODE_CODE,
        status=status,
        expires_at=NOW_UTC + timedelta(hours=1),
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
        source_friend_challenge_id=None,
    )


def _baseline_attempt(*, duel_id: UUID) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=11,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
        score=None,
        time_ms=None,
        result=None,
        completed_at=None,
        created_at=NOW_UTC,
    )


def _challenger_attempt(*, duel_id: UUID) -> ArenaAttempt:
    return ArenaAttempt(
        id=uuid4(),
        arena_duel_id=duel_id,
        user_id=22,
        role=ARENA_ATTEMPT_ROLE_CHALLENGER,
        score=None,
        time_ms=None,
        result=None,
        completed_at=None,
        created_at=NOW_UTC,
    )


@pytest.mark.asyncio
async def test_create_arena_duel_baseline_creates_draft_attempt_and_starts_round_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def _fake_select_questions(*_args, **kwargs):
        captured["select_questions"] = kwargs
        return _question_ids()

    async def _fake_create_duel(*_args, **kwargs):
        captured["duel"] = kwargs["duel"]
        return kwargs["duel"]

    async def _fake_create_attempt(*_args, **kwargs):
        captured["attempt"] = kwargs["attempt"]
        return kwargs["attempt"]

    async def _fake_start_session(*_args, **kwargs):
        captured["start_session"] = kwargs
        return _start_result()

    monkeypatch.setattr(arena_service, "select_duel_question_ids", _fake_select_questions)
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_duel", _fake_create_duel)
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_attempt", _fake_create_attempt)
    monkeypatch.setattr(arena_service, "start_session", _fake_start_session)

    result = await arena_service.create_arena_duel_baseline(
        AsyncSessionStub(),
        creator_user_id=11,
        mode_code=MODE_CODE,
        now_utc=NOW_UTC,
        duel_limit_checked=True,
    )

    duel = captured["duel"]
    attempt = captured["attempt"]
    start_kwargs = cast(dict[str, object], captured["start_session"])
    select_kwargs = cast(dict[str, object], captured["select_questions"])

    assert isinstance(duel, ArenaDuel)
    assert isinstance(attempt, ArenaAttempt)
    assert duel.status == ARENA_DUEL_STATUS_DRAFT
    assert duel.question_ids == _question_ids()
    assert duel.baseline_attempt_id is None
    assert attempt.arena_duel_id == duel.id
    assert attempt.role == ARENA_ATTEMPT_ROLE_CREATOR_BASELINE
    assert start_kwargs["source"] == ARENA_SOURCE
    assert start_kwargs["arena_attempt_id"] == attempt.id
    assert start_kwargs["arena_round"] == 1
    assert start_kwargs["duel_limit_checked"] is True
    assert select_kwargs["total_rounds"] == 7
    assert select_kwargs["challenge_seed"] == str(duel.id)
    assert result.baseline_attempt_id == attempt.id
    assert result.duel.status == ARENA_DUEL_STATUS_DRAFT


@pytest.mark.asyncio
async def test_create_arena_duel_baseline_requires_duel_limit_before_creating_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_create(*_args, **_kwargs):
        pytest.fail("Arena rows must not be created before the duel-limit gate")

    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_duel", _unexpected_create)
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "create_attempt", _unexpected_create)

    with pytest.raises(DuelLimitRequiredError):
        await arena_service.create_arena_duel_baseline(
            AsyncSessionStub(),
            creator_user_id=11,
            mode_code=MODE_CODE,
            now_utc=NOW_UTC,
            duel_limit_checked=False,
        )


@pytest.mark.asyncio
async def test_complete_arena_creator_baseline_publishes_active_for_24_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = _duel()
    attempt = _baseline_attempt(duel_id=duel.id)

    async def _fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=duel)

    async def _fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=7, score=6, time_ms=48_000)

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", _fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", _fake_summary)

    result = await arena_service.complete_arena_creator_baseline(
        AsyncSessionStub(),
        attempt_id=attempt.id,
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert attempt.score == 6
    assert attempt.time_ms == 48_000
    assert attempt.result == ARENA_ATTEMPT_RESULT_BASELINE
    assert attempt.completed_at == NOW_UTC
    assert duel.status == ARENA_DUEL_STATUS_ACTIVE
    assert duel.baseline_attempt_id == attempt.id
    assert duel.expires_at == NOW_UTC + timedelta(hours=24)
    assert result.baseline_score == 6
    assert result.baseline_time_ms == 48_000


@pytest.mark.asyncio
async def test_complete_arena_creator_baseline_if_applicable_ignores_challengers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = _duel(status=ARENA_DUEL_STATUS_ACTIVE)
    attempt = _challenger_attempt(duel_id=duel.id)

    async def _fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=duel)

    async def _unexpected_summary(*_args, **_kwargs):
        pytest.fail("challenger final round must not publish creator baseline")

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", _fake_get_context
    )
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "summarize_completed_attempt", _unexpected_summary
    )

    result = await arena_service.complete_arena_creator_baseline_if_applicable(
        AsyncSessionStub(),
        attempt_id=attempt.id,
        user_id=22,
        now_utc=NOW_UTC,
    )

    assert result is None


@pytest.mark.asyncio
async def test_complete_arena_creator_baseline_rejects_incomplete_round_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = _duel()
    attempt = _baseline_attempt(duel_id=duel.id)

    async def _fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=duel)

    async def _fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=6, score=6, time_ms=42_000)

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", _fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", _fake_summary)

    with pytest.raises(ArenaDuelIncompleteError):
        await arena_service.complete_arena_creator_baseline(
            AsyncSessionStub(),
            attempt_id=attempt.id,
            user_id=11,
            now_utc=NOW_UTC,
        )

    assert duel.status == ARENA_DUEL_STATUS_DRAFT
    assert duel.baseline_attempt_id is None
    assert attempt.score is None
    assert attempt.time_ms is None
    assert attempt.completed_at is None


@pytest.mark.asyncio
async def test_list_active_arena_duels_maps_complete_baselines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = _duel(status=ARENA_DUEL_STATUS_ACTIVE)
    attempt = _baseline_attempt(duel_id=duel.id)
    duel.baseline_attempt_id = attempt.id
    attempt.score = 7
    attempt.time_ms = 55_000
    attempt.completed_at = NOW_UTC

    async def _fake_rows(*_args, **_kwargs):
        return [ArenaActiveDuelRow(duel=duel, baseline_attempt=attempt)]

    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "list_active_with_baseline", _fake_rows)

    result = await arena_service.list_active_arena_duels(AsyncSessionStub(), now_utc=NOW_UTC)

    assert len(result) == 1
    assert result[0].duel_id == duel.id
    assert result[0].baseline_attempt_id == attempt.id
    assert result[0].score == 7
    assert result[0].time_ms == 55_000
    assert result[0].question_ids == tuple(_question_ids())


@pytest.mark.asyncio
async def test_arena_baseline_summary_counts_each_completed_round_once() -> None:
    attempt_id = uuid4()
    session = _OneRowRecordingSession((7, 6, 48_000))

    summary = await ArenaDuelsRepo.summarize_completed_attempt(session, attempt_id=attempt_id)

    assert summary.completed_rounds == 7
    assert summary.score == 6
    assert summary.time_ms == 48_000
    assert session.statement is not None
    compiled = session.statement.compile()
    sql = str(compiled)
    assert "row_number() OVER" in sql
    assert "PARTITION BY quiz_sessions.arena_round" in sql
    assert "ORDER BY quiz_attempts.answered_at ASC, quiz_attempts.id ASC" in sql
    assert "count(anon_1.arena_round)" in sql
    assert "count(quiz_attempts.id)" not in sql
    assert compiled.params["arena_attempt_id_1"] == attempt_id
    assert compiled.params["attempt_rank_1"] == 1


@pytest.mark.asyncio
async def test_active_arena_repo_listing_requires_publish_ready_baseline() -> None:
    session = _RecordingSession()

    await ArenaDuelsRepo.list_active_with_baseline(session, now_utc=NOW_UTC, limit=3)

    assert session.statement is not None
    compiled = session.statement.compile()
    sql = str(compiled)
    assert compiled.params["status_1"] == ARENA_DUEL_STATUS_ACTIVE
    assert compiled.params["role_1"] == ARENA_ATTEMPT_ROLE_CREATOR_BASELINE
    assert "arena_duels.status = :status_1" in sql
    assert "arena_duels.expires_at > :expires_at_1" in sql
    assert "arena_duels.baseline_attempt_id IS NOT NULL" in sql
    assert "arena_duels.question_ids IS NOT NULL" in sql
    assert "arena_attempts.role = :role_1" in sql
    assert "arena_attempts.score IS NOT NULL" in sql
    assert "arena_attempts.time_ms IS NOT NULL" in sql
    assert "arena_attempts.completed_at IS NOT NULL" in sql


class _EmptyRows:
    def all(self) -> list[object]:
        return []


class _OneRow:
    def __init__(self, row: tuple[int, int, int]) -> None:
        self._row = row

    def one(self) -> tuple[int, int, int]:
        return self._row


class _RecordingSession(AsyncSessionStub):
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyRows()


class _OneRowRecordingSession(AsyncSessionStub):
    def __init__(self, row: tuple[int, int, int]) -> None:
        self.statement = None
        self._row = row

    async def execute(self, statement):
        self.statement = statement
        return _OneRow(self._row)
