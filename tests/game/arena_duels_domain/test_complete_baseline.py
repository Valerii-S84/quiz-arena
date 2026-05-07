from datetime import timedelta

import pytest

from app.db.repo.arena_duels_repo import ArenaAttemptCompletionSummary, ArenaAttemptDuelContext
from app.game.arena_duels import service as arena_service
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_EXPIRED,
)
from app.game.arena_duels.errors import ArenaDuelIncompleteError
from tests.type_helpers import AsyncSessionStub

from .support import NOW_UTC, baseline_attempt, challenger_attempt, duel


@pytest.mark.asyncio
async def test_complete_arena_creator_baseline_publishes_active_for_24_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel()
    attempt = baseline_attempt(duel_id=current_duel.id)

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=7, score=6, time_ms=48_000)

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", fake_summary)

    result = await arena_service.complete_arena_creator_baseline(
        AsyncSessionStub(), attempt_id=attempt.id, user_id=11, now_utc=NOW_UTC
    )

    assert attempt.score == 6
    assert attempt.time_ms == 48_000
    assert attempt.result == ARENA_ATTEMPT_RESULT_BASELINE
    assert attempt.completed_at == NOW_UTC
    assert current_duel.status == ARENA_DUEL_STATUS_ACTIVE
    assert current_duel.baseline_attempt_id == attempt.id
    assert current_duel.expires_at == NOW_UTC + timedelta(hours=24)
    assert result.baseline_score == 6
    assert result.baseline_time_ms == 48_000


@pytest.mark.asyncio
async def test_complete_arena_creator_baseline_allows_attempt_after_worker_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_EXPIRED)
    current_duel.expires_at = NOW_UTC - timedelta(minutes=1)
    attempt = baseline_attempt(duel_id=current_duel.id)
    attempt.created_at = NOW_UTC - timedelta(hours=1)

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=7, score=6, time_ms=48_000)

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", fake_summary)

    result = await arena_service.complete_arena_creator_baseline(
        AsyncSessionStub(), attempt_id=attempt.id, user_id=11, now_utc=NOW_UTC
    )

    assert current_duel.status == ARENA_DUEL_STATUS_ACTIVE
    assert current_duel.expires_at == NOW_UTC + timedelta(hours=24)
    assert result.baseline_attempt_id == attempt.id


@pytest.mark.asyncio
async def test_complete_arena_creator_baseline_if_applicable_ignores_challengers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_ACTIVE)
    attempt = challenger_attempt(duel_id=current_duel.id)

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def unexpected_summary(*_args, **_kwargs):
        pytest.fail("challenger final round must not publish creator baseline")

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "summarize_completed_attempt", unexpected_summary
    )

    result = await arena_service.complete_arena_creator_baseline_if_applicable(
        AsyncSessionStub(), attempt_id=attempt.id, user_id=22, now_utc=NOW_UTC
    )

    assert result is None


@pytest.mark.asyncio
async def test_complete_arena_creator_baseline_rejects_incomplete_round_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel()
    attempt = baseline_attempt(duel_id=current_duel.id)

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=6, score=6, time_ms=42_000)

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", fake_summary)

    with pytest.raises(ArenaDuelIncompleteError):
        await arena_service.complete_arena_creator_baseline(
            AsyncSessionStub(), attempt_id=attempt.id, user_id=11, now_utc=NOW_UTC
        )

    assert current_duel.baseline_attempt_id is None
    assert attempt.score is None
    assert attempt.time_ms is None
    assert attempt.completed_at is None
