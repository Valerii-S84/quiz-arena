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


def _run(*, status: str = "IN_PROGRESS", completed_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        current_question=0,
        status=status,
        completed_at=completed_at,
    )


def _question() -> SimpleNamespace:
    return SimpleNamespace(
        question_id="daily-q-edge",
        text="Question?",
        options=("a", "b", "c", "d"),
        category="Daily",
    )


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("duplicate"))


@pytest.mark.asyncio
async def test_emit_daily_blocked_emits_expected_analytics_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict[str, object]] = []

    async def _fake_emit_analytics_event(*_args, **kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(sessions_start_daily, "emit_analytics_event", _fake_emit_analytics_event)

    await sessions_start_daily._emit_daily_blocked(
        SimpleNamespace(),
        user_id=21,
        berlin_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert events == [
        {
            "event_type": "daily_blocked_already_played",
            "source": sessions_start_daily.EVENT_SOURCE_BOT,
            "happened_at": NOW_UTC,
            "user_id": 21,
            "payload": {"berlin_date": BERLIN_DATE.isoformat()},
        }
    ]


@pytest.mark.asyncio
async def test_create_or_resume_daily_run_returns_created_run_when_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_run = _run()

    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "get_by_user_date_for_update",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "create",
        _async_return(created_run),
    )

    run, started_now = await sessions_start_daily._create_or_resume_daily_run(
        SimpleNamespace(),
        user_id=22,
        berlin_date=BERLIN_DATE,
        now_utc=NOW_UTC,
    )

    assert run is created_run
    assert started_now is True


@pytest.mark.asyncio
async def test_create_or_resume_daily_run_reraises_when_integrity_error_cannot_recover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_calls = {"count": 0}

    async def _fake_get_by_user_date_for_update(*_args, **_kwargs):
        get_calls["count"] += 1
        return None

    async def _fake_create(*_args, **_kwargs):
        raise _integrity_error()

    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "get_by_user_date_for_update",
        _fake_get_by_user_date_for_update,
    )
    monkeypatch.setattr(sessions_start_daily.DailyRunsRepo, "create", _fake_create)

    with pytest.raises(IntegrityError):
        await sessions_start_daily._create_or_resume_daily_run(
            SimpleNamespace(),
            user_id=23,
            berlin_date=BERLIN_DATE,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_create_or_resume_daily_run_blocks_when_integrity_error_loads_completed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked: list[dict[str, object]] = []
    loaded = _run(status="COMPLETED", completed_at=NOW_UTC)
    get_calls = {"count": 0}

    async def _fake_get_by_user_date_for_update(*_args, **_kwargs):
        get_calls["count"] += 1
        if get_calls["count"] == 1:
            return None
        return loaded

    async def _fake_create(*_args, **_kwargs):
        raise _integrity_error()

    async def _fake_emit_daily_blocked(*_args, **kwargs) -> None:
        blocked.append(kwargs)

    monkeypatch.setattr(
        sessions_start_daily.DailyRunsRepo,
        "get_by_user_date_for_update",
        _fake_get_by_user_date_for_update,
    )
    monkeypatch.setattr(sessions_start_daily.DailyRunsRepo, "create", _fake_create)
    monkeypatch.setattr(sessions_start_daily, "_emit_daily_blocked", _fake_emit_daily_blocked)

    with pytest.raises(DailyChallengeAlreadyPlayedError):
        await sessions_start_daily._create_or_resume_daily_run(
            SimpleNamespace(),
            user_id=24,
            berlin_date=BERLIN_DATE,
            now_utc=NOW_UTC,
        )

    assert blocked == [
        {
            "user_id": 24,
            "berlin_date": BERLIN_DATE,
            "now_utc": NOW_UTC,
        }
    ]


@pytest.mark.asyncio
async def test_start_daily_session_reraises_when_quiz_session_integrity_error_has_no_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sessions_start_daily,
        "_create_or_resume_daily_run",
        _async_return((_run(), False)),
    )
    monkeypatch.setattr(
        sessions_start_daily.QuizSessionsRepo,
        "get_active_daily_session_for_run",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_start_daily,
        "resolve_daily_question_for_position",
        _async_return(("daily-q-edge", _question())),
    )
    monkeypatch.setattr(
        sessions_start_daily.QuizSessionsRepo,
        "create",
        _raise_integrity_error,
    )

    with pytest.raises(IntegrityError):
        await sessions_start_daily.start_daily_session(
            SimpleNamespace(),
            user_id=25,
            idempotency_key="daily:edge",
            local_date=BERLIN_DATE,
            now_utc=NOW_UTC,
        )


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


async def _raise_integrity_error(*_args, **_kwargs):
    raise _integrity_error()
