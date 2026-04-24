from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import daily_flow
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult
from tests.bot.helpers import DummyCallback, DummyMessage

NOW_UTC = datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc)


class _SessionBegin:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionLocal:
    def __init__(self, session: object) -> None:
        self._session = session

    def begin(self) -> _SessionBegin:
        return _SessionBegin(self._session)


@pytest.mark.parametrize(
    ("correct", "expected"),
    [
        (0, "✅ 0/7 — noch 7 für ein Duell-Ticket!"),
        (1, "✅ 1/7 — noch 6 für ein Duell-Ticket!"),
        (6, "✅ 6/7 — noch 1 für ein Duell-Ticket!"),
        (7, None),
    ],
)
def test_build_daily_ticket_progress_text_uses_correct_total_and_left(
    correct: int,
    expected: str | None,
) -> None:
    assert daily_flow._build_daily_ticket_progress_text(correct=correct, total=7) == expected


@pytest.mark.asyncio
async def test_handle_daily_answer_branch_adds_ticket_progress_and_next_question() -> None:
    session = object()
    callback = DummyCallback(
        data="answer:x",
        from_user=SimpleNamespace(id=21),
        message=DummyMessage(),
    )
    result = AnswerSessionResult(
        session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        question_id="daily-q-4",
        is_correct=True,
        current_streak=3,
        best_streak=5,
        idempotent_replay=False,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        selected_answer_text="A",
        correct_answer_text="A",
        daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        daily_current_question=4,
        daily_total_questions=7,
        daily_score=4,
        daily_completed=False,
    )

    async def _fake_snapshot(_session, *, telegram_user):
        assert _session is session
        assert telegram_user.id == 21
        return SimpleNamespace(user_id=7, free_energy=20, paid_energy=0)

    async def _fake_start_session(_session, **kwargs):
        assert _session is session
        assert kwargs["user_id"] == 7
        return SimpleNamespace(
            session=SimpleNamespace(
                session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                options=("a", "b", "c", "d"),
            )
        )

    await daily_flow.handle_daily_answer_branch(
        callback,
        result=result,
        now_utc=NOW_UTC,
        session_local=_SessionLocal(session),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_fake_snapshot),
        game_session_service=SimpleNamespace(start_session=_fake_start_session),
        build_question_text=cast(object, lambda **kwargs: "next-question"),
    )

    assert callback.message.answers[0].text == (
        f'{TEXTS_DE["msg.daily.answer.progress.correct"].format(current=4, total=7)}\n'
        f'{TEXTS_DE["msg.daily.answer.reward_progress"].format(correct=4, total=7, left=3)}'
    )
    assert callback.message.answers[1].text == "next-question"
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_daily_answer_branch_hides_ticket_progress_after_perfect_run() -> None:
    callback = DummyCallback(
        data="answer:x",
        from_user=SimpleNamespace(id=21),
        message=DummyMessage(),
    )
    result = AnswerSessionResult(
        session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        question_id="daily-q-7",
        is_correct=True,
        current_streak=7,
        best_streak=9,
        idempotent_replay=False,
        mode_code="DAILY_CHALLENGE",
        source="DAILY_CHALLENGE",
        selected_answer_text="A",
        correct_answer_text="A",
        daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        daily_current_question=7,
        daily_total_questions=7,
        daily_score=7,
        daily_completed=True,
    )

    await daily_flow.handle_daily_answer_branch(
        callback,
        result=result,
        now_utc=NOW_UTC,
        session_local=SimpleNamespace(),
        user_onboarding_service=SimpleNamespace(),
        game_session_service=SimpleNamespace(),
        build_question_text=cast(object, lambda **kwargs: "unused"),
    )

    assert callback.message.answers[0].text == TEXTS_DE["msg.daily.answer.progress.correct"].format(
        current=7,
        total=7,
    )
    assert callback.message.answers[1].text == TEXTS_DE["msg.daily.result.reward.ticket"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
