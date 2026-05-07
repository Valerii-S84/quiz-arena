from __future__ import annotations

from tests.game.sessions_submit_daily_support import (
    BERLIN_DATE,
    NOW_UTC,
    QuizSession,
    SimpleNamespace,
    _async_return,
    _Session,
    cast,
    pytest,
    sessions_submit_daily,
    uuid4,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_correct", "initial_score", "expected_score"),
    [
        (True, 6, 7),
        (True, 5, 6),
        (True, 4, 5),
        (False, 4, 4),
    ],
)
async def test_apply_daily_answer_completes_with_expected_reward_score_and_preserves_streak_flow(
    monkeypatch: pytest.MonkeyPatch,
    is_correct: bool,
    initial_score: int,
    expected_score: int,
) -> None:
    reward_calls: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    quiz_session = cast(QuizSession, SimpleNamespace(daily_run_id=uuid4()))
    run = SimpleNamespace(
        id=quiz_session.daily_run_id,
        berlin_date=BERLIN_DATE,
        current_question=6,
        score=initial_score,
        status="IN_PROGRESS",
        completed_at=None,
    )

    async def _fake_apply_reward(*_args, **kwargs) -> None:
        reward_calls.append(kwargs)

    async def _fake_record_activity(*_args, **_kwargs):
        return SimpleNamespace(current_streak=6, best_streak=8)

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(
        sessions_submit_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _async_return(run),
    )
    monkeypatch.setattr(
        sessions_submit_daily,
        "_apply_daily_completion_reward",
        _fake_apply_reward,
    )
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "record_activity",
        _fake_record_activity,
    )
    monkeypatch.setattr(
        sessions_submit_daily,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )

    state = await sessions_submit_daily.apply_daily_answer(
        _Session(),
        user_id=11,
        quiz_session=quiz_session,
        is_correct=is_correct,
        now_utc=NOW_UTC,
    )

    assert reward_calls == [
        {
            "user_id": 11,
            "daily_run_id": run.id,
            "score": expected_score,
            "now_utc": NOW_UTC,
        }
    ]
    assert state.completed is True
    assert state.current_question == 7
    assert state.score == expected_score
    assert state.current_streak == 6
    assert state.best_streak == 8
    assert run.status == "COMPLETED"
    assert run.completed_at == NOW_UTC
    payload = cast(dict[str, object], events[0]["payload"])
    assert payload["score"] == expected_score


@pytest.mark.asyncio
async def test_apply_daily_answer_does_not_repeat_reward_for_already_completed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = cast(QuizSession, SimpleNamespace(daily_run_id=uuid4()))
    run = SimpleNamespace(
        id=quiz_session.daily_run_id,
        berlin_date=BERLIN_DATE,
        current_question=7,
        score=6,
        status="COMPLETED",
        completed_at=NOW_UTC,
    )

    async def _unexpected_apply_reward(*_args, **_kwargs) -> None:
        pytest.fail("reward should not be re-applied for completed daily runs")

    async def _unexpected_record_activity(*_args, **_kwargs):
        pytest.fail("streak activity should not be re-recorded for completed daily runs")

    async def _fake_sync_rollover(*_args, **_kwargs):
        return SimpleNamespace(current_streak=3, best_streak=5)

    monkeypatch.setattr(
        sessions_submit_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _async_return(run),
    )
    monkeypatch.setattr(
        sessions_submit_daily,
        "_apply_daily_completion_reward",
        _unexpected_apply_reward,
    )
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "record_activity",
        _unexpected_record_activity,
    )
    monkeypatch.setattr(
        sessions_submit_daily.StreakService,
        "sync_rollover",
        _fake_sync_rollover,
    )

    state = await sessions_submit_daily.apply_daily_answer(
        _Session(),
        user_id=11,
        quiz_session=quiz_session,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert state.daily_run_id == run.id
    assert state.current_question == 7
    assert state.score == 6
    assert state.completed is True
    assert state.current_streak == 3
    assert state.best_streak == 5
    assert run.status == "COMPLETED"
