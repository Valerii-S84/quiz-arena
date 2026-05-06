from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.service import question_loading
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


def _session(*, source: str, question_id: str | None = "q-1", daily_run_id=None) -> QuizSession:
    return QuizSession(
        id=uuid4(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2" if source != "DAILY_CHALLENGE" else "DAILY_CHALLENGE",
        source=source,
        status="STARTED",
        energy_cost_total=0,
        question_id=question_id,
        daily_run_id=daily_run_id,
        friend_challenge_id=uuid4() if source == "FRIEND_CHALLENGE" else None,
        friend_challenge_round=2 if source == "FRIEND_CHALLENGE" else None,
        arena_attempt_id=uuid4() if source == "ARENA_DUEL" else None,
        arena_round=3 if source == "ARENA_DUEL" else None,
        started_at=NOW_UTC,
        local_date_berlin=NOW_UTC.date(),
        idempotency_key=f"session:{uuid4()}",
    )


@pytest.mark.asyncio
async def test_infer_preferred_level_uses_latest_active_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        question_loading.QuizAttemptsRepo,
        "get_recent_question_ids_for_mode",
        _async_return(["q-1"]),
    )
    monkeypatch.setattr(
        question_loading.QuizQuestionsRepo,
        "get_by_id",
        _async_return(SimpleNamespace(status="ACTIVE", level=" a2 ")),
    )

    assert (
        await question_loading._infer_preferred_level_from_recent_attempt(
            AsyncSessionStub(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
        )
        == "A2"
    )


@pytest.mark.asyncio
async def test_infer_preferred_level_returns_none_without_recent_or_active_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        question_loading.QuizAttemptsRepo,
        "get_recent_question_ids_for_mode",
        _async_return([]),
    )
    assert (
        await question_loading._infer_preferred_level_from_recent_attempt(
            AsyncSessionStub(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
        )
        is None
    )

    monkeypatch.setattr(
        question_loading.QuizAttemptsRepo,
        "get_recent_question_ids_for_mode",
        _async_return(["q-1"]),
    )
    monkeypatch.setattr(
        question_loading.QuizQuestionsRepo,
        "get_by_id",
        _async_return(SimpleNamespace(status="DISABLED", level="A2")),
    )
    assert (
        await question_loading._infer_preferred_level_from_recent_attempt(
            AsyncSessionStub(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
        )
        is None
    )


@pytest.mark.asyncio
async def test_load_question_for_session_falls_back_to_mode_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.game.sessions.service.get_question_by_id", _async_return(None))
    monkeypatch.setattr(
        "app.game.sessions.service.get_question_for_mode",
        _async_return(
            SimpleNamespace(question_id="fallback-q", text="Q?", options=("a",), category="Gen")
        ),
    )

    question = await question_loading._load_question_for_session(
        AsyncSessionStub(),
        quiz_session=_session(source="MENU"),
    )

    assert question.question_id == "fallback-q"


@pytest.mark.asyncio
async def test_build_start_result_from_existing_session_sets_source_specific_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        question_loading,
        "_load_question_for_session",
        _async_return(
            SimpleNamespace(question_id="q-1", text="Q?", options=("a",), category="Gen")
        ),
    )
    monkeypatch.setattr(
        question_loading.FriendChallengesRepo,
        "get_by_id",
        _async_return(SimpleNamespace(total_rounds=7)),
    )
    monkeypatch.setattr(
        question_loading.DailyRunsRepo,
        "get_by_id",
        _async_return(SimpleNamespace(current_question=6)),
    )

    friend = await question_loading._build_start_result_from_existing_session(
        AsyncSessionStub(),
        existing=_session(source="FRIEND_CHALLENGE"),
        idempotent_replay=True,
    )
    arena = await question_loading._build_start_result_from_existing_session(
        AsyncSessionStub(),
        existing=_session(source="ARENA_DUEL"),
        idempotent_replay=True,
    )
    daily = await question_loading._build_start_result_from_existing_session(
        AsyncSessionStub(),
        existing=_session(source="DAILY_CHALLENGE", daily_run_id=uuid4()),
        idempotent_replay=False,
    )

    assert (friend.session.question_number, friend.session.total_questions) == (2, 7)
    assert (arena.session.question_number, arena.session.total_questions) == (3, 7)
    assert (daily.session.question_number, daily.session.total_questions) == (7, 7)


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
