from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import SessionNotFoundError
from app.game.sessions.types import (
    AnswerSessionResult,
    FriendChallengeSnapshot,
    SessionQuestionView,
    StartSessionResult,
)
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


def _challenge_snapshot(*, status: str = "ACTIVE", winner_user_id: int | None = None) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        invite_token="token",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        status=status,
        creator_user_id=10,
        opponent_user_id=20,
        current_round=3,
        total_rounds=12,
        creator_score=5,
        opponent_score=4,
        winner_user_id=winner_user_id,
    )


def _start_result() -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            question_id="q-1",
            text="Frage?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
        ),
        energy_free=18,
        energy_paid=2,
        idempotent_replay=False,
    )


def test_format_user_label_prefers_username_then_first_name() -> None:
    assert gameplay._format_user_label(username="alice", first_name="Alice") == "@alice"
    assert gameplay._format_user_label(username=" ", first_name="Alice") == "Alice"
    assert gameplay._format_user_label(username=None, first_name=" ") == "Freund"


def test_build_friend_score_text_handles_creator_and_completed_round() -> None:
    challenge = _challenge_snapshot(status="COMPLETED")
    text = gameplay._build_friend_score_text(
        challenge=challenge,
        user_id=10,
        opponent_label="Bob",
    )
    assert "Du 5" in text
    assert "Bob 4" in text
    assert "12/12" in text


def test_build_friend_finish_text_handles_win_and_draw() -> None:
    win_text = gameplay._build_friend_finish_text(
        challenge=_challenge_snapshot(status="COMPLETED", winner_user_id=10),
        user_id=10,
        opponent_label="Bob",
    )
    draw_text = gameplay._build_friend_finish_text(
        challenge=_challenge_snapshot(status="COMPLETED", winner_user_id=None),
        user_id=10,
        opponent_label="Bob",
    )
    assert TEXTS_DE["msg.friend.challenge.finished.win"] in win_text
    assert TEXTS_DE["msg.friend.challenge.finished.draw"] in draw_text


@pytest.mark.asyncio
async def test_build_friend_invite_link_returns_none_on_bot_error() -> None:
    message = DummyMessage()
    message.bot.raise_on_get_me = True
    callback = DummyCallback(
        data="x",
        from_user=SimpleNamespace(id=1),
        message=message,
    )
    assert await gameplay._build_friend_invite_link(callback, invite_token="abc") is None


@pytest.mark.asyncio
async def test_handle_game_stop_with_missing_message_returns_error() -> None:
    callback = DummyCallback(data="game:stop", from_user=SimpleNamespace(id=1))
    callback.message = None

    await gameplay.handle_game_stop(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_mode_with_missing_data_returns_error() -> None:
    callback = DummyCallback(data=None, from_user=SimpleNamespace(id=1))

    await gameplay.handle_mode(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_answer_rejects_missing_callback_fields() -> None:
    callback = DummyCallback(data=None, from_user=None)

    await gameplay.handle_answer(callback)  # type: ignore[arg-type]

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


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
        )

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:2",
        from_user=SimpleNamespace(id=9),
    )
    await gameplay.handle_answer(callback)

    assert any(call.text == TEXTS_DE["msg.game.daily.finished"] for call in callback.message.answers)


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
