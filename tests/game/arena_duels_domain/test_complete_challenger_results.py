from datetime import timedelta

import pytest

from app.db.repo.arena_duels_repo import ArenaAttemptCompletionSummary, ArenaAttemptDuelContext
from app.game.arena_duels import service as arena_service
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_LOSS,
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_DUEL_STATUS_ACTIVE,
    ARENA_DUEL_STATUS_EXPIRED,
)
from tests.type_helpers import AsyncSessionStub

from .support import NOW_UTC, challenger_attempt, completed_attempt, duel


@pytest.mark.asyncio
async def test_complete_arena_challenger_without_new_best_sends_no_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_ACTIVE)
    previous_best = completed_attempt(
        duel_id=current_duel.id,
        user_id=11,
        score=6,
        time_ms=48_000,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    )
    attempt = challenger_attempt(duel_id=current_duel.id)
    current_duel.baseline_attempt_id = previous_best.id

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=7, score=5, time_ms=44_000)

    async def fake_completed_attempts(*_args, **_kwargs):
        return [previous_best]

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", fake_summary)
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "list_completed_attempts_for_duel", fake_completed_attempts
    )

    result = await arena_service.complete_arena_attempt_if_applicable(
        AsyncSessionStub(), attempt_id=attempt.id, user_id=22, now_utc=NOW_UTC
    )

    assert result is not None
    assert result.beaten_notification is None
    assert result.completed_attempt is not None
    assert result.opponent_attempt is not None
    assert result.completed_attempt.score == 5
    assert result.completed_attempt.time_ms == 44_000
    assert result.opponent_attempt.score == 6
    assert result.opponent_attempt.time_ms == 48_000
    assert attempt.result == ARENA_ATTEMPT_RESULT_LOSS


@pytest.mark.asyncio
async def test_complete_arena_challenger_allows_attempt_after_worker_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_EXPIRED)
    current_duel.expires_at = NOW_UTC - timedelta(minutes=1)
    previous_best = completed_attempt(
        duel_id=current_duel.id,
        user_id=11,
        score=6,
        time_ms=48_000,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    )
    attempt = challenger_attempt(duel_id=current_duel.id)
    attempt.created_at = NOW_UTC - timedelta(hours=1)
    current_duel.baseline_attempt_id = previous_best.id

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=7, score=5, time_ms=44_000)

    async def fake_completed_attempts(*_args, **_kwargs):
        return [previous_best]

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", fake_summary)
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "list_completed_attempts_for_duel", fake_completed_attempts
    )

    result = await arena_service.complete_arena_attempt_if_applicable(
        AsyncSessionStub(), attempt_id=attempt.id, user_id=22, now_utc=NOW_UTC
    )

    assert result is not None
    assert result.completed_attempt is not None
    assert result.completed_attempt.score == 5
    assert attempt.completed_at == NOW_UTC


@pytest.mark.asyncio
async def test_complete_arena_challenger_repeat_suppresses_result_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_ACTIVE)
    baseline = completed_attempt(
        duel_id=current_duel.id,
        user_id=11,
        score=6,
        time_ms=48_000,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    )
    attempt = completed_attempt(duel_id=current_duel.id, user_id=22, score=7, time_ms=52_000)
    attempt.result = ARENA_ATTEMPT_RESULT_WIN
    current_duel.baseline_attempt_id = baseline.id

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def unexpected_summary(*_args, **_kwargs):
        pytest.fail("idempotent challenger completion must not resummarize rounds")

    async def unexpected_completed_attempts(*_args, **_kwargs):
        pytest.fail("idempotent challenger completion must not derive opponent from leaderboard")

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "summarize_completed_attempt", unexpected_summary
    )
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo,
        "list_completed_attempts_for_duel",
        unexpected_completed_attempts,
    )

    result = await arena_service.complete_arena_attempt_if_applicable(
        AsyncSessionStub(), attempt_id=attempt.id, user_id=22, now_utc=NOW_UTC
    )

    assert result is not None
    assert result.completed_attempt is None
    assert result.opponent_attempt is None
    assert result.beaten_notification is None
