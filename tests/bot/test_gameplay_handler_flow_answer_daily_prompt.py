from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult
from tests.bot.helpers import DummyCallback, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_answer_daily_branch_shows_referral_prompt_when_reserved(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())
    emitted_events: list[str] = []
    daily_branch_called = False

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77, free_energy=11, paid_energy=2, current_streak=3)

    async def _fake_submit_answer(*args, **kwargs):
        del args, kwargs
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-daily",
            is_correct=True,
            current_streak=7,
            best_streak=10,
            idempotent_replay=False,
            mode_code="DAILY_CHALLENGE",
            source="DAILY_CHALLENGE",
            selected_answer_text="der",
            correct_answer_text="der",
            daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            daily_current_question=7,
            daily_total_questions=7,
            daily_score=6,
            daily_completed=True,
        )

    async def _fake_reserve_prompt(session, *, user_id: int, now_utc):
        del session, user_id, now_utc
        return True

    async def _fake_show_channel_bonus(session, *, user_id: int, idempotent_replay: bool):
        del session, user_id, idempotent_replay
        return False

    async def _fake_emit(*args, **kwargs):
        emitted_events.append(kwargs["event_type"])
        del args, kwargs
        return None

    async def _fake_daily_branch(*args, **kwargs):
        nonlocal daily_branch_called
        del args, kwargs
        daily_branch_called = True
        return None

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)
    monkeypatch.setattr(gameplay.ReferralService, "reserve_post_game_prompt", _fake_reserve_prompt)
    monkeypatch.setattr(
        gameplay.ChannelBonusService,
        "should_show_post_game_prompt",
        _fake_show_channel_bonus,
    )
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)
    monkeypatch.setattr(gameplay.daily_flow, "handle_daily_answer_branch", _fake_daily_branch)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:2",
        from_user=SimpleNamespace(id=9),
    )
    await gameplay.handle_answer(callback)

    assert daily_branch_called is True
    prompt_call = next(
        call
        for call in callback.message.answers
        if call.text == TEXTS_DE["msg.referral.prompt.after_game"]
    )
    callbacks = [
        button.callback_data
        for row in prompt_call.kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["referral:prompt:share", "referral:prompt:later"]
    assert "referral_prompt_shown" in emitted_events
