from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.errors import SessionNotFoundError, TournamentSessionStopNotAllowedError
from app.game.sessions.service import sessions_daily

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
BERLIN_DATE = date(2026, 3, 14)


def _quiz_session(
    *,
    user_id: int = 11,
    status: str = "STARTED",
    source: str = "DAILY_CHALLENGE",
    daily_run_id=None,
    friend_challenge_id=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status=status,
        source=source,
        daily_run_id=daily_run_id,
        friend_challenge_id=friend_challenge_id,
        completed_at=None,
    )


def _daily_run(
    *,
    user_id: int = 11,
    status: str = "IN_PROGRESS",
    current_question: int = 3,
    score: int = 2,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        berlin_date=BERLIN_DATE,
        score=score,
        current_question=current_question,
        status=status,
        completed_at=NOW_UTC,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quiz_session",
    [
        None,
        _quiz_session(user_id=99),
    ],
)
async def test_abandon_session_rejects_missing_or_foreign_session(
    monkeypatch: pytest.MonkeyPatch,
    quiz_session: SimpleNamespace | None,
) -> None:
    monkeypatch.setattr(
        sessions_daily.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )

    with pytest.raises(SessionNotFoundError):
        await sessions_daily.abandon_session(
            SimpleNamespace(),
            user_id=11,
            session_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_abandon_session_rejects_tournament_friend_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge_id = uuid4()
    quiz_session = _quiz_session(friend_challenge_id=challenge_id)
    challenge = SimpleNamespace(tournament_match_id=uuid4())

    monkeypatch.setattr(
        sessions_daily.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(
        sessions_daily.FriendChallengesRepo,
        "get_by_id",
        _async_return(challenge),
    )

    with pytest.raises(TournamentSessionStopNotAllowedError):
        await sessions_daily.abandon_session(
            SimpleNamespace(),
            user_id=11,
            session_id=quiz_session.id,
            now_utc=NOW_UTC,
        )

    assert quiz_session.status == "STARTED"
    assert quiz_session.completed_at is None


@pytest.mark.asyncio
async def test_abandon_session_returns_without_changes_when_not_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = _quiz_session(status="COMPLETED")

    async def _unexpected_emit(*_args, **_kwargs) -> None:
        pytest.fail("daily_abandoned should not be emitted for non-started sessions")

    monkeypatch.setattr(
        sessions_daily.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(sessions_daily, "emit_analytics_event", _unexpected_emit)

    await sessions_daily.abandon_session(
        SimpleNamespace(),
        user_id=11,
        session_id=quiz_session.id,
        now_utc=NOW_UTC,
    )

    assert quiz_session.status == "COMPLETED"
    assert quiz_session.completed_at is None


@pytest.mark.asyncio
async def test_abandon_session_marks_non_daily_session_without_daily_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = _quiz_session(source="MENU", daily_run_id=None)

    async def _unexpected_emit(*_args, **_kwargs) -> None:
        pytest.fail("daily_abandoned should not be emitted for non-daily sessions")

    monkeypatch.setattr(
        sessions_daily.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(
        sessions_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _unexpected_async("daily run lookup should not happen for non-daily session"),
    )
    monkeypatch.setattr(sessions_daily, "emit_analytics_event", _unexpected_emit)

    await sessions_daily.abandon_session(
        SimpleNamespace(),
        user_id=11,
        session_id=quiz_session.id,
        now_utc=NOW_UTC,
    )

    assert quiz_session.status == "ABANDONED"
    assert quiz_session.completed_at == NOW_UTC


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "run",
    [
        None,
        _daily_run(status="COMPLETED"),
    ],
)
async def test_abandon_session_skips_daily_run_updates_when_missing_or_completed(
    monkeypatch: pytest.MonkeyPatch,
    run: SimpleNamespace | None,
) -> None:
    quiz_session = _quiz_session(daily_run_id=uuid4())

    async def _unexpected_emit(*_args, **_kwargs) -> None:
        pytest.fail("daily_abandoned should not be emitted when run is missing or completed")

    monkeypatch.setattr(
        sessions_daily.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(
        sessions_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _async_return(run),
    )
    monkeypatch.setattr(sessions_daily, "emit_analytics_event", _unexpected_emit)

    await sessions_daily.abandon_session(
        SimpleNamespace(),
        user_id=11,
        session_id=quiz_session.id,
        now_utc=NOW_UTC,
    )

    assert quiz_session.status == "ABANDONED"
    assert quiz_session.completed_at == NOW_UTC
    if run is not None:
        assert run.status == "COMPLETED"


@pytest.mark.asyncio
async def test_abandon_session_marks_daily_run_abandoned_and_emits_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    run = _daily_run(status="IN_PROGRESS")
    quiz_session = _quiz_session(daily_run_id=run.id)

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(
        sessions_daily.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(
        sessions_daily.DailyRunsRepo,
        "get_by_id_for_update",
        _async_return(run),
    )
    monkeypatch.setattr(sessions_daily, "emit_analytics_event", _fake_emit_analytics_event)

    await sessions_daily.abandon_session(
        SimpleNamespace(),
        user_id=11,
        session_id=quiz_session.id,
        now_utc=NOW_UTC,
    )

    assert quiz_session.status == "ABANDONED"
    assert quiz_session.completed_at == NOW_UTC
    assert run.status == "ABANDONED"
    assert run.completed_at is None
    assert events == [
        {
            "event_type": "daily_abandoned",
            "source": sessions_daily.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 11,
            "payload": {
                "daily_run_id": str(run.id),
                "berlin_date": run.berlin_date.isoformat(),
                "current_question": run.current_question,
                "score": run.score,
            },
        }
    ]


@pytest.mark.asyncio
async def test_get_daily_run_summary_returns_summary_for_owner_and_rejects_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _daily_run(user_id=11, status="IN_PROGRESS")

    monkeypatch.setattr(sessions_daily.DailyRunsRepo, "get_by_id", _async_return(run))

    summary = await sessions_daily.get_daily_run_summary(
        SimpleNamespace(),
        user_id=11,
        daily_run_id=run.id,
    )

    assert summary.daily_run_id == run.id
    assert summary.berlin_date == run.berlin_date
    assert summary.score == run.score
    assert summary.total_questions == sessions_daily.DAILY_CHALLENGE_TOTAL_QUESTIONS
    assert summary.status == run.status

    with pytest.raises(SessionNotFoundError):
        await sessions_daily.get_daily_run_summary(
            SimpleNamespace(),
            user_id=99,
            daily_run_id=run.id,
        )


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _unexpected_async(message: str):
    async def _inner(*_args, **_kwargs):
        pytest.fail(message)

    return _inner
