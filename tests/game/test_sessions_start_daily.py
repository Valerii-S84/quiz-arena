from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.game.sessions.errors import DailyChallengeAlreadyPlayedError
from app.game.sessions.service import sessions_start_daily

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
BERLIN_DATE = date(2026, 3, 14)


def _question() -> SimpleNamespace:
    return SimpleNamespace(
        question_id="daily-q-1",
        text="Question?",
        options=("a", "b", "c", "d"),
        category="Daily",
    )


def _run(
    *,
    current_question: int = 0,
    status: str = "IN_PROGRESS",
    completed_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        current_question=current_question,
        status=status,
        completed_at=completed_at,
    )


def _session(*, session_id=None) -> SimpleNamespace:
    return SimpleNamespace(id=session_id or uuid4())


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("duplicate"))


@pytest.mark.asyncio
async def test_create_or_resume_daily_run_blocks_completed_existing_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked: list[dict[str, object]] = []
    existing = _run(current_question=7, status="COMPLETED", completed_at=NOW_UTC)

    async def _fake_emit_daily_blocked(*_args, **kwargs) -> None:
        blocked.append(kwargs)

    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "get_by_user_date_for_update",
        lambda *_args, **_kwargs: _async_return(existing)(),
    )
    monkeypatch.setattr(sessions_start_daily, "_emit_daily_blocked", _fake_emit_daily_blocked)

    with pytest.raises(DailyChallengeAlreadyPlayedError):
        await sessions_start_daily._create_or_resume_daily_run(
            SimpleNamespace(),
            user_id=11,
            berlin_date=BERLIN_DATE,
            now_utc=NOW_UTC,
        )

    assert blocked == [
        {
            "user_id": 11,
            "berlin_date": BERLIN_DATE,
            "now_utc": NOW_UTC,
        }
    ]


@pytest.mark.asyncio
async def test_create_or_resume_daily_run_resumes_abandoned_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _run(status="ABANDONED", completed_at=NOW_UTC)

    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "get_by_user_date_for_update",
        lambda *_args, **_kwargs: _async_return(existing)(),
    )

    run, started_now = await sessions_start_daily._create_or_resume_daily_run(
        SimpleNamespace(),
        user_id=11,
        berlin_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert run is existing
    assert started_now is False
    assert existing.status == "IN_PROGRESS"
    assert existing.completed_at is None


@pytest.mark.asyncio
async def test_create_or_resume_daily_run_returns_existing_in_progress_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _run(status="IN_PROGRESS", completed_at=None)

    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "get_by_user_date_for_update",
        _async_return(existing),
    )

    run, started_now = await sessions_start_daily._create_or_resume_daily_run(
        SimpleNamespace(),
        user_id=11,
        berlin_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert run is existing
    assert started_now is False
    assert existing.status == "IN_PROGRESS"
    assert existing.completed_at is None


@pytest.mark.asyncio
async def test_create_or_resume_daily_run_recovers_integrity_error_with_loaded_abandoned_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _run(status="ABANDONED", completed_at=NOW_UTC)
    get_calls = {"count": 0}

    async def _fake_get_by_user_date_for_update(*_args, **_kwargs):
        get_calls["count"] += 1
        if get_calls["count"] == 1:
            return None
        return loaded

    async def _fake_create(*_args, **_kwargs):
        raise _integrity_error()

    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "get_by_user_date_for_update",
        _fake_get_by_user_date_for_update,
    )
    monkeypatch.setattr(sessions_start_daily.DailyRunsRepo, "create", _fake_create)

    run, started_now = await sessions_start_daily._create_or_resume_daily_run(
        SimpleNamespace(),
        user_id=12,
        berlin_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert run is loaded
    assert started_now is False
    assert loaded.status == "IN_PROGRESS"
    assert loaded.completed_at is None


@pytest.mark.asyncio
async def test_start_daily_session_blocks_when_run_is_already_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked: list[dict[str, object]] = []
    run = _run(current_question=7, status="IN_PROGRESS")

    async def _fake_emit_daily_blocked(*_args, **kwargs) -> None:
        blocked.append(kwargs)

    monkeypatch.setattr(
        sessions_start_daily,
        "_create_or_resume_daily_run",
        _async_return((run, False)),
    )
    monkeypatch.setattr(sessions_start_daily, "_emit_daily_blocked", _fake_emit_daily_blocked)

    with pytest.raises(DailyChallengeAlreadyPlayedError):
        await sessions_start_daily.start_daily_session(
            SimpleNamespace(),
            user_id=13,
            idempotency_key="daily:overflow",
            local_date=BERLIN_DATE,
            now_utc=NOW_UTC,
        )

    assert run.status == "COMPLETED"
    assert run.completed_at == NOW_UTC
    assert blocked == [
        {
            "user_id": 13,
            "berlin_date": BERLIN_DATE,
            "now_utc": NOW_UTC,
        }
    ]


@pytest.mark.asyncio
async def test_start_daily_session_reuses_active_session_without_started_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_session = _session()
    expected = object()

    async def _fake_build_start_result(*_args, **kwargs):
        assert kwargs["existing"] is active_session
        assert kwargs["idempotent_replay"] is False
        return expected

    async def _unexpected_emit(*_args, **_kwargs) -> None:
        pytest.fail("daily_started should not be emitted for resumed active session")

    monkeypatch.setattr(
        sessions_start_daily,
        "_create_or_resume_daily_run",
        _async_return((_run(current_question=1), False)),
    )
    monkeypatch.setattr(
        sessions_start_daily.QuizSessionsRepo,
        "get_active_daily_session_for_run",
        _async_return(active_session),
    )
    monkeypatch.setattr(
        sessions_start_daily,
        "_build_start_result_from_existing_session",
        _fake_build_start_result,
    )
    monkeypatch.setattr(sessions_start_daily, "emit_analytics_event", _unexpected_emit)

    result = await sessions_start_daily.start_daily_session(
        SimpleNamespace(),
        user_id=14,
        idempotency_key="daily:reuse",
        local_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert result is expected


@pytest.mark.asyncio
async def test_start_daily_session_recovers_after_quiz_session_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recovered_session = _session()
    result_sentinel = object()
    question = _question()
    active_calls = {"count": 0}

    async def _fake_get_active_daily_session_for_run(*_args, **_kwargs):
        active_calls["count"] += 1
        if active_calls["count"] == 1:
            return None
        return recovered_session

    async def _fake_create(*_args, **_kwargs):
        raise _integrity_error()

    async def _fake_build_start_result(*_args, **kwargs):
        assert kwargs["existing"] is recovered_session
        assert kwargs["idempotent_replay"] is False
        return result_sentinel

    monkeypatch.setattr(
        sessions_start_daily,
        "_create_or_resume_daily_run",
        _async_return((_run(current_question=0), False)),
    )
    monkeypatch.setattr(
        sessions_start_daily.QuizSessionsRepo,
        "get_active_daily_session_for_run",
        _fake_get_active_daily_session_for_run,
    )
    monkeypatch.setattr(
        sessions_start_daily,
        "resolve_daily_question_for_position",
        _async_return((question.question_id, question)),
    )
    monkeypatch.setattr(sessions_start_daily.QuizSessionsRepo, "create", _fake_create)
    monkeypatch.setattr(
        sessions_start_daily,
        "_build_start_result_from_existing_session",
        _fake_build_start_result,
    )

    result = await sessions_start_daily.start_daily_session(
        SimpleNamespace(),
        user_id=15,
        idempotency_key="daily:recover-session",
        local_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert result is result_sentinel


@pytest.mark.asyncio
async def test_start_daily_session_emits_started_event_only_for_new_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []
    question = _question()
    created_session = _session()
    run = _run(current_question=0)

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(
        sessions_start_daily,
        "_create_or_resume_daily_run",
        _async_return((run, True)),
    )
    monkeypatch.setattr(
        sessions_start_daily.QuizSessionsRepo,
        "get_active_daily_session_for_run",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_start_daily,
        "resolve_daily_question_for_position",
        _async_return((question.question_id, question)),
    )
    monkeypatch.setattr(
        sessions_start_daily.QuizSessionsRepo,
        "create",
        _async_return(created_session),
    )
    monkeypatch.setattr(sessions_start_daily, "emit_analytics_event", _fake_emit_analytics_event)

    result = await sessions_start_daily.start_daily_session(
        SimpleNamespace(),
        user_id=16,
        idempotency_key="daily:new-run",
        local_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert result.idempotent_replay is False
    assert result.session.session_id == created_session.id
    assert result.session.question_id == question.question_id
    assert result.session.question_number == 1
    assert result.session.total_questions == sessions_start_daily.DAILY_CHALLENGE_TOTAL_QUESTIONS
    assert events == [
        {
            "event_type": "daily_started",
            "source": sessions_start_daily.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 16,
            "payload": {
                "daily_run_id": str(run.id),
                "berlin_date": BERLIN_DATE.isoformat(),
            },
        }
    ]


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
