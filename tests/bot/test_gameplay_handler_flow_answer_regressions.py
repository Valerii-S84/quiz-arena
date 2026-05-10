from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import InvalidAnswerOptionError
from app.game.sessions.types import AnswerSessionResult
from tests.bot.helpers import DummyCallback, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_answer_rejects_unparseable_answer_callback() -> None:
    callback = DummyCallback(data="answer:not-a-session:1", from_user=SimpleNamespace(id=1))

    await gameplay.handle_answer(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]
    assert callback.message.answers == []


@pytest.mark.asyncio
async def test_handle_answer_reports_invalid_answer_option(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=1, free_energy=10, paid_energy=0, current_streak=0)

    async def _fake_submit_answer(*args, **kwargs):
        del args, kwargs
        raise InvalidAnswerOptionError()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:3",
        from_user=SimpleNamespace(id=1),
    )
    await gameplay.handle_answer(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.system.error"]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_handle_answer_sends_home_when_answer_result_has_no_active_mode(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())
    captured: dict[str, str] = {}

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=12, free_energy=10, paid_energy=0, current_streak=0)

    async def _fake_submit_answer(*args, **kwargs):
        del args, kwargs
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-stopped",
            is_correct=False,
            current_streak=0,
            best_streak=0,
            idempotent_replay=False,
            mode_code=None,
            source=None,
        )

    async def _fake_send_home_message(message, *, text: str) -> None:
        del message
        captured["text"] = text

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)
    monkeypatch.setattr(gameplay.answer_flow, "_send_home_message", _fake_send_home_message)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=12),
    )
    await gameplay.handle_answer(callback)

    assert captured["text"] == TEXTS_DE["msg.game.stopped"]
    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
