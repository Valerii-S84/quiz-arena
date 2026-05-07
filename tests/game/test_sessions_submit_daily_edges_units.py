from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.service import sessions_submit_daily
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


def _quiz_session(*, daily_run_id=None) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=11,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        status="COMPLETED",
        energy_cost_total=0,
        question_id="q-1",
        daily_run_id=daily_run_id,
        started_at=NOW_UTC,
        local_date_berlin=NOW_UTC.date(),
        idempotency_key=f"session:{uuid4()}",
    )


@pytest.mark.asyncio
async def test_credit_daily_duel_ticket_raises_when_product_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sessions_submit_daily.PurchasesRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )
    monkeypatch.setattr(sessions_submit_daily, "get_product", lambda _code: None)
    monkeypatch.setattr(
        sessions_submit_daily,
        "_get_purchase_service",
        lambda: SimpleNamespace(_build_purchase=None, apply_zero_cost_purchase=None),
    )

    with pytest.raises(ValueError, match="ticket product is not configured"):
        await sessions_submit_daily._credit_daily_duel_ticket(
            AsyncSessionStub(),
            user_id=11,
            daily_run_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_build_daily_replay_state_handles_missing_run_id_and_missing_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_run = await sessions_submit_daily.build_daily_replay_state(
        AsyncSessionStub(),
        replay_session=_quiz_session(daily_run_id=None),
        current_streak=1,
        best_streak=2,
    )
    assert no_run.daily_run_id is None
    assert no_run.current_question == 0

    replay_session = _quiz_session(daily_run_id=uuid4())
    monkeypatch.setattr(sessions_submit_daily.DailyRunsRepo, "get_by_id", _async_return(None))
    missing_run = await sessions_submit_daily.build_daily_replay_state(
        AsyncSessionStub(),
        replay_session=replay_session,
        current_streak=3,
        best_streak=4,
    )
    assert missing_run.daily_run_id == replay_session.daily_run_id
    assert missing_run.score == 0
    assert missing_run.completed is False


@pytest.mark.asyncio
async def test_build_daily_replay_state_uses_existing_run_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_session = _quiz_session(daily_run_id=uuid4())
    run = SimpleNamespace(
        id=replay_session.daily_run_id,
        current_question=6,
        score=5,
        status="COMPLETED",
    )
    monkeypatch.setattr(sessions_submit_daily.DailyRunsRepo, "get_by_id", _async_return(run))

    state = await sessions_submit_daily.build_daily_replay_state(
        AsyncSessionStub(),
        replay_session=replay_session,
        current_streak=4,
        best_streak=9,
    )

    assert state.daily_run_id == run.id
    assert state.current_question == 6
    assert state.score == 5
    assert state.completed is True
    assert state.current_streak == 4


@pytest.mark.asyncio
async def test_apply_daily_answer_handles_missing_daily_run_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "sync_rollover",
        _async_return(SimpleNamespace(current_streak=5, best_streak=7)),
    )

    state = await sessions_submit_daily.apply_daily_answer(
        AsyncSessionStub(),
        user_id=11,
        quiz_session=_quiz_session(daily_run_id=None),
        is_correct=True,
        now_utc=NOW_UTC,
    )
    assert state.daily_run_id is None
    assert state.score == 1
    assert state.current_streak == 5


@pytest.mark.asyncio
async def test_apply_daily_answer_handles_missing_run_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daily_run_id = uuid4()
    monkeypatch.setattr(
        sessions_submit_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "sync_rollover",
        _async_return(SimpleNamespace(current_streak=2, best_streak=3)),
    )

    state = await sessions_submit_daily.apply_daily_answer(
        AsyncSessionStub(),
        user_id=11,
        quiz_session=_quiz_session(daily_run_id=daily_run_id),
        is_correct=False,
        now_utc=NOW_UTC,
    )
    assert state.daily_run_id == daily_run_id
    assert state.score == 0
    assert state.current_streak == 2


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
