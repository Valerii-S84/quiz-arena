from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import SessionNotFoundError
from app.game.sessions.types import AnswerSessionResult, FriendChallengeSnapshot
from tests.bot.gameplay_flow_fixtures import _start_result
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_handle_answer_handles_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=1, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_submit_answer(*args, **kwargs):
        raise SessionNotFoundError()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:1",
        from_user=SimpleNamespace(id=1),
    )
    await gameplay.handle_answer(callback)

    assert callback.message.answers[0].text == TEXTS_DE["msg.game.session.not_found"]


@pytest.mark.asyncio
async def test_handle_answer_finishes_daily_challenge(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=9, free_energy=11, paid_energy=2, current_streak=3)

    async def _fake_submit_answer(*args, **kwargs):
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

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:2",
        from_user=SimpleNamespace(id=9),
    )
    await gameplay.handle_answer(callback)

    assert any("🏆 Heute: 6/7 richtig" in (call.text or "") for call in callback.message.answers)


@pytest.mark.asyncio
async def test_handle_answer_finishes_daily_challenge_hides_streak_when_zero(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=9, free_energy=11, paid_energy=2, current_streak=0)

    async def _fake_submit_answer(*args, **kwargs):
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-daily",
            is_correct=True,
            current_streak=0,
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

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:2",
        from_user=SimpleNamespace(id=9),
    )
    await gameplay.handle_answer(callback)

    result_messages = [call.text or "" for call in callback.message.answers]
    assert any("🏆 Heute: 6/7 richtig" in text for text in result_messages)
    assert all("🔥 Streak:" not in text for text in result_messages)


@pytest.mark.asyncio
async def test_handle_answer_daily_in_progress_sends_progress_and_next_question(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=9, free_energy=11, paid_energy=2, current_streak=3)

    async def _fake_submit_answer(*args, **kwargs):
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-daily",
            is_correct=False,
            current_streak=7,
            best_streak=10,
            idempotent_replay=False,
            mode_code="DAILY_CHALLENGE",
            source="DAILY_CHALLENGE",
            selected_answer_text="der",
            correct_answer_text="die Küche",
            daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            daily_current_question=4,
            daily_total_questions=7,
            daily_score=2,
            daily_completed=False,
        )

    async def _fake_start_session(*args, **kwargs):
        return _start_result()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)
    monkeypatch.setattr(gameplay.GameSessionService, "start_session", _fake_start_session)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:2",
        from_user=SimpleNamespace(id=9),
    )
    await gameplay.handle_answer(callback)

    assert any("(4/7)" in (call.text or "") for call in callback.message.answers)
    assert any(call.kwargs.get("parse_mode") == "HTML" for call in callback.message.answers)


@pytest.mark.asyncio
async def test_handle_answer_daily_idempotent_replay_is_silent(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=9, free_energy=11, paid_energy=2, current_streak=3)

    async def _fake_submit_answer(*args, **kwargs):
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-daily",
            is_correct=True,
            current_streak=3,
            best_streak=10,
            idempotent_replay=True,
            mode_code="DAILY_CHALLENGE",
            source="DAILY_CHALLENGE",
            selected_answer_text=None,
            correct_answer_text=None,
            daily_run_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            daily_current_question=1,
            daily_total_questions=7,
            daily_score=1,
            daily_completed=False,
        )

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:2",
        from_user=SimpleNamespace(id=9),
    )
    await gameplay.handle_answer(callback)

    assert callback.message.answers == []


@pytest.mark.asyncio
async def test_handle_answer_starts_next_round_for_regular_mode(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=12, free_energy=19, paid_energy=1, current_streak=5)

    async def _fake_submit_answer(*args, **kwargs):
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-main",
            is_correct=False,
            current_streak=2,
            best_streak=8,
            idempotent_replay=False,
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            selected_answer_text="die",
            correct_answer_text="der",
            next_preferred_level="A2",
        )

    async def _fake_start_session(*args, **kwargs):
        return _start_result()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)
    monkeypatch.setattr(gameplay.GameSessionService, "start_session", _fake_start_session)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=12),
    )
    await gameplay.handle_answer(callback)

    assert any(call.kwargs.get("parse_mode") == "HTML" for call in callback.message.answers)


@pytest.mark.asyncio
async def test_handle_answer_friend_challenge_completion_sends_proof_card_with_share_button(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_submit_answer(*args, **kwargs):
        return AnswerSessionResult(
            session_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            question_id="q-friend",
            is_correct=True,
            current_streak=4,
            best_streak=7,
            idempotent_replay=False,
            mode_code="QUICK_MIX_A1A2",
            source="FRIEND_CHALLENGE",
            selected_answer_text="der",
            correct_answer_text="der",
            friend_challenge=FriendChallengeSnapshot(
                challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_token="token",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="COMPLETED",
                creator_user_id=10,
                opponent_user_id=20,
                current_round=5,
                total_rounds=5,
                creator_score=4,
                opponent_score=2,
                winner_user_id=10,
            ),
            friend_challenge_answered_round=5,
            friend_challenge_round_completed=True,
            friend_challenge_waiting_for_opponent=False,
        )

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge
        return "Bob" if user_id == 10 else "Alice"

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback, opponent_user_id, text, reply_markup
        return

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)
    monkeypatch.setattr(gameplay, "_notify_opponent", _fake_notify)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(bot=DummyBot(username="proofbot")),
    )
    await gameplay.handle_answer(callback)

    finish_call = next(
        call
        for call in callback.message.answers
        if call.text and TEXTS_DE["msg.friend.challenge.proof.title"] in call.text
    )
    assert TEXTS_DE["msg.friend.challenge.finished.win"] in (finish_call.text or "")
    keyboard = finish_call.kwargs["reply_markup"]
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:share:result:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
