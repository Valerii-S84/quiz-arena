import pytest

from app.db.repo.arena_duels_repo import ArenaAttemptCompletionSummary, ArenaAttemptDuelContext
from app.game.arena_duels import service as arena_service
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_WIN,
    ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    ARENA_BEATEN_NOTIFICATION_TYPE,
    ARENA_DUEL_STATUS_ACTIVE,
)
from tests.type_helpers import AsyncSessionStub

from .support import NOW_UTC, challenger_attempt, completed_attempt, duel


@pytest.mark.asyncio
async def test_complete_arena_challenger_notifies_previous_best_holder_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_duel = duel(status=ARENA_DUEL_STATUS_ACTIVE)
    original_creator = completed_attempt(
        duel_id=current_duel.id,
        user_id=11,
        score=6,
        time_ms=48_000,
        role=ARENA_ATTEMPT_ROLE_CREATOR_BASELINE,
    )
    previous_best = completed_attempt(duel_id=current_duel.id, user_id=22, score=7, time_ms=52_000)
    attempt = challenger_attempt(duel_id=current_duel.id)
    attempt.user_id = 33
    current_duel.baseline_attempt_id = original_creator.id

    async def fake_get_context(*_args, **_kwargs):
        return ArenaAttemptDuelContext(attempt=attempt, duel=current_duel)

    async def fake_summary(*_args, **_kwargs):
        return ArenaAttemptCompletionSummary(completed_rounds=7, score=7, time_ms=50_000)

    async def fake_completed_attempts(*_args, **_kwargs):
        return [previous_best, original_creator]

    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "get_attempt_duel_for_update", fake_get_context
    )
    monkeypatch.setattr(arena_service.ArenaDuelsRepo, "summarize_completed_attempt", fake_summary)
    monkeypatch.setattr(
        arena_service.ArenaDuelsRepo, "list_completed_attempts_for_duel", fake_completed_attempts
    )

    result = await arena_service.complete_arena_attempt_if_applicable(
        AsyncSessionStub(), attempt_id=attempt.id, user_id=33, now_utc=NOW_UTC
    )

    assert result is not None
    assert result.beaten_notification is not None
    assert result.beaten_notification.previous_best_user_id == 22
    assert result.beaten_notification.previous_best_attempt_id == previous_best.id
    assert result.beaten_notification.new_best_user_id == 33
    assert result.beaten_notification.notification_type == ARENA_BEATEN_NOTIFICATION_TYPE
    assert attempt.result == ARENA_ATTEMPT_RESULT_WIN
