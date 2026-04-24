from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.game.sessions.service import sessions_submit
from app.game.sessions.types import AnswerSessionResult
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc)


class _Session(AsyncSessionStub):
    pass


def _replay_result() -> AnswerSessionResult:
    return AnswerSessionResult(
        session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        question_id="daily-q-7",
        is_correct=True,
        current_streak=4,
        best_streak=6,
        idempotent_replay=True,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        daily_current_question=7,
        daily_total_questions=7,
        daily_score=6,
        daily_completed=True,
    )


@pytest.mark.asyncio
async def test_submit_answer_reuses_existing_attempt_without_reapplying_daily_reward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_attempt = SimpleNamespace(
        session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        question_id="daily-q-7",
        is_correct=True,
    )
    replay_session = SimpleNamespace(
        id=existing_attempt.session_id,
        source="DAILY_CHALLENGE",
        mode_code="DAILY_CHALLENGE",
        question_id="daily-q-7",
    )
    replay_result = _replay_result()

    async def _unexpected_apply_daily_answer(*_args, **_kwargs):
        pytest.fail("daily reward flow should not run for replayed submits")

    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "get_by_idempotency_key",
        _async_return(existing_attempt),
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id",
        _async_return(replay_session),
    )
    monkeypatch.setattr(
        sessions_submit,
        "build_replay_answer_result",
        _async_return(replay_result),
    )
    monkeypatch.setattr(
        sessions_submit,
        "apply_daily_answer",
        _unexpected_apply_daily_answer,
    )

    result = await sessions_submit.submit_answer(
        _Session(),
        user_id=11,
        session_id=uuid4(),
        selected_option=1,
        idempotency_key="answer:duplicate",
        now_utc=NOW_UTC,
    )

    assert result is replay_result


@pytest.mark.asyncio
async def test_submit_answer_replays_completed_daily_session_without_reapplying_reward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quiz_session = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        user_id=11,
        source="DAILY_CHALLENGE",
        status="COMPLETED",
    )
    latest_attempt = SimpleNamespace(
        session_id=quiz_session.id,
        question_id="daily-q-7",
        is_correct=True,
    )
    replay_result = _replay_result()

    async def _unexpected_apply_daily_answer(*_args, **_kwargs):
        pytest.fail("daily reward flow should not run for completed daily sessions")

    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "get_by_idempotency_key",
        _async_return(None),
    )
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo,
        "get_by_id_for_update",
        _async_return(quiz_session),
    )
    monkeypatch.setattr(
        sessions_submit.QuizAttemptsRepo,
        "get_latest_for_session",
        _async_return(latest_attempt),
    )
    monkeypatch.setattr(
        sessions_submit,
        "build_replay_answer_result",
        _async_return(replay_result),
    )
    monkeypatch.setattr(
        sessions_submit,
        "apply_daily_answer",
        _unexpected_apply_daily_answer,
    )

    result = await sessions_submit.submit_answer(
        _Session(),
        user_id=11,
        session_id=quiz_session.id,
        selected_option=1,
        idempotency_key="answer:completed-replay",
        now_utc=NOW_UTC,
    )

    assert result is replay_result


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
