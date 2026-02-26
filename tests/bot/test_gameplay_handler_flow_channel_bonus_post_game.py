from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult
from tests.bot.gameplay_flow_fixtures import _start_result
from tests.bot.helpers import DummyCallback, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_answer_shows_channel_bonus_and_skips_referral_prompt(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())
    emitted_events: list[str] = []

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=12, free_energy=19, paid_energy=1, current_streak=5)

    async def _fake_submit_answer(*args, **kwargs):
        del args, kwargs
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-main",
            is_correct=True,
            current_streak=2,
            best_streak=8,
            idempotent_replay=False,
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            selected_answer_text="die",
            correct_answer_text="die",
            next_preferred_level="A2",
        )

    async def _fake_start_session(*args, **kwargs):
        del args, kwargs
        return _start_result()

    async def _fake_show_channel_bonus(session, *, user_id: int, idempotent_replay: bool):
        del session, user_id, idempotent_replay
        return True

    async def _fail_referral_prompt(*args, **kwargs):
        raise AssertionError("referral prompt must be skipped when channel bonus is shown")

    async def _fake_emit(*args, **kwargs):
        emitted_events.append(str(kwargs["event_type"]))
        del args, kwargs
        return None

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)
    monkeypatch.setattr(gameplay.GameSessionService, "start_session", _fake_start_session)
    monkeypatch.setattr(
        gameplay.ChannelBonusService,
        "should_show_post_game_prompt",
        _fake_show_channel_bonus,
    )
    monkeypatch.setattr(
        gameplay.ReferralService,
        "reserve_post_game_prompt",
        _fail_referral_prompt,
    )
    monkeypatch.setattr(gameplay.ChannelBonusService, "resolve_channel_url", lambda: None)
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=12),
    )
    await gameplay.handle_answer(callback)

    assert any(
        call.text is not None and "Lerne täglich kostenlos Deutsch" in call.text
        for call in callback.message.answers
    )
    assert all(
        call.text != TEXTS_DE["msg.referral.prompt.after_game"] for call in callback.message.answers
    )
    assert "channel_bonus_shown" in emitted_events
