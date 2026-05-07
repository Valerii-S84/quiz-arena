from uuid import uuid4

import pytest

from app.db.repo.arena_duels_repo import ArenaActiveDuelRow, ArenaDuelsRepo
from app.game.arena_duels import service as arena_service
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
)
from tests.type_helpers import AsyncSessionStub

from .support import (
    NOW_UTC,
    OneRowRecordingSession,
    RecordingSession,
    baseline_attempt,
    completed_attempt,
    duel,
    question_ids,
)


@pytest.mark.asyncio
async def test_list_active_arena_duels_maps_complete_baselines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_ACTIVE)
    attempt = baseline_attempt(duel_id=current_duel.id)
    current_duel.baseline_attempt_id = attempt.id
    attempt.score = 7
    attempt.time_ms = 55_000
    attempt.completed_at = NOW_UTC

    async def fake_rows(*_args, **_kwargs):
        return [ArenaActiveDuelRow(duel=current_duel, baseline_attempt=attempt)]

    async def fake_completed_attempts(*_args, **_kwargs):
        return [attempt]

    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "list_active_with_baseline", fake_rows)
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo,
        "list_completed_attempts_for_duel",
        fake_completed_attempts,
    )

    result = await arena_service.list_active_arena_duels(AsyncSessionStub(), now_utc=NOW_UTC)

    assert len(result) == 1
    assert result[0].duel_id == current_duel.id
    assert result[0].baseline_attempt_id == attempt.id
    assert result[0].score == 7
    assert result[0].time_ms == 55_000
    assert result[0].question_ids == tuple(question_ids())


@pytest.mark.asyncio
async def test_list_active_arena_duels_maps_current_best_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_ACTIVE)
    baseline = baseline_attempt(duel_id=current_duel.id)
    current_duel.baseline_attempt_id = baseline.id
    baseline.score = 6
    baseline.time_ms = 48_000
    baseline.completed_at = NOW_UTC
    current_best = completed_attempt(duel_id=current_duel.id, user_id=33, score=7, time_ms=52_000)

    async def fake_rows(*_args, **_kwargs):
        return [ArenaActiveDuelRow(duel=current_duel, baseline_attempt=baseline)]

    async def fake_completed_attempts(*_args, **_kwargs):
        return [current_best, baseline]

    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "list_active_with_baseline", fake_rows)
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo,
        "list_completed_attempts_for_duel",
        fake_completed_attempts,
    )

    result = await arena_service.list_active_arena_duels(AsyncSessionStub(), now_utc=NOW_UTC)

    assert len(result) == 1
    assert result[0].duel_id == current_duel.id
    assert result[0].creator_user_id == 33
    assert result[0].baseline_attempt_id == current_best.id
    assert result[0].score == 7
    assert result[0].time_ms == 52_000


@pytest.mark.asyncio
async def test_arena_baseline_summary_counts_each_completed_round_once() -> None:
    attempt_id = uuid4()
    session = OneRowRecordingSession((7, 6, 48_000))

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
    session = RecordingSession()

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
