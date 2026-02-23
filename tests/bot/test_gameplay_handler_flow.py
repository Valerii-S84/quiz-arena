from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import FriendChallengeExpiredError, SessionNotFoundError
from app.game.sessions.types import (
    AnswerSessionResult,
    FriendChallengeSnapshot,
    SessionQuestionView,
    StartSessionResult,
)
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage, DummySessionLocal


def _challenge_snapshot(
    *, status: str = "ACTIVE", winner_user_id: int | None = None
) -> FriendChallengeSnapshot:
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
            category="Artikel - Nominativ",
            question_number=3,
            total_questions=12,
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
    expired_text = gameplay._build_friend_finish_text(
        challenge=_challenge_snapshot(status="EXPIRED", winner_user_id=None),
        user_id=10,
        opponent_label="Bob",
    )
    assert TEXTS_DE["msg.friend.challenge.finished.win"] in win_text
    assert TEXTS_DE["msg.friend.challenge.finished.draw"] in draw_text
    assert TEXTS_DE["msg.friend.challenge.finished.expired"] in expired_text


def test_build_friend_proof_card_text_includes_winner_score_and_signature() -> None:
    proof_text = gameplay._build_friend_proof_card_text(
        challenge=_challenge_snapshot(status="COMPLETED", winner_user_id=10),
        user_id=10,
        opponent_label="Bob",
    )
    assert TEXTS_DE["msg.friend.challenge.proof.title"] in proof_text
    assert "Sieger: Du" in proof_text
    assert "Score: Du 5 | Bob 4" in proof_text
    assert "Titel:" in proof_text


def test_build_question_text_contains_theme_counter_and_energy() -> None:
    text = gameplay._build_question_text(
        source="MENU",
        snapshot_free_energy=18,
        snapshot_paid_energy=2,
        start_result=_start_result(),
    )
    assert "⚡" in text
    assert "🔋 Energie:" in text
    assert "📚 Thema:" in text
    assert "❓ Frage 3/12" in text


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
async def test_build_friend_result_share_url_returns_none_on_bot_error() -> None:
    message = DummyMessage()
    message.bot.raise_on_get_me = True
    callback = DummyCallback(
        data="x",
        from_user=SimpleNamespace(id=1),
        message=message,
    )
    share_url = await gameplay._build_friend_result_share_url(
        callback,
        proof_card_text="proof card",
    )
    assert share_url is None


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_opens_format_picker(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    callback = DummyCallback(
        data="friend:challenge:create",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_create(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.create.choose"]
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:challenge:create:3" in callbacks
    assert "friend:challenge:create:5" in callbacks
    assert "friend:challenge:create:12" in callbacks


@pytest.mark.asyncio
async def test_handle_friend_challenge_create_selected_hides_raw_url_and_keeps_share_link(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=17)

    async def _fake_create_friend_challenge(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="0123456789abcdef0123456789abcdef",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACTIVE",
            creator_user_id=17,
            opponent_user_id=None,
            current_round=1,
            total_rounds=5,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    async def _fake_friend_invite_link(callback, *, invite_token: str):
        assert invite_token == "0123456789abcdef0123456789abcdef"
        return "https://t.me/testbot?start=fc_0123456789abcdef0123456789abcdef"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "create_friend_challenge",
        _fake_create_friend_challenge,
    )
    monkeypatch.setattr(gameplay, "_build_friend_invite_link", _fake_friend_invite_link)

    callback = DummyCallback(
        data="friend:challenge:create:5",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_create_selected(callback)

    response = callback.message.answers[0]
    assert "https://t.me/" not in (response.text or "")
    keyboard = response.kwargs["reply_markup"]
    share_urls = [button.url for row in keyboard.inline_keyboard for button in row if button.url]
    assert any("start%3Dfc_0123456789abcdef0123456789abcdef" in url for url in share_urls)
    assert len(share_urls) == 3


@pytest.mark.asyncio
async def test_handle_friend_challenge_rematch_creates_duel_and_notifies_opponent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10)

    async def _fake_rematch(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            invite_token="token-rematch",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACTIVE",
            creator_user_id=10,
            opponent_user_id=20,
            current_round=1,
            total_rounds=5,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    notified: list[int] = []

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback, text, reply_markup
        notified.append(opponent_user_id)

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge
        return "Bob" if user_id == 10 else "Alice"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService, "create_friend_challenge_rematch", _fake_rematch
    )
    monkeypatch.setattr(gameplay, "_notify_opponent", _fake_notify)
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)

    callback = DummyCallback(
        data="friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_rematch(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.friend.challenge.rematch.created"].format(opponent_label="Bob") in (
        response.text or ""
    )
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:next:cccccccc-cccc-cccc-cccc-cccccccccccc" in callbacks
    assert notified == [20]


@pytest.mark.asyncio
async def test_handle_friend_challenge_series_best3_creates_duel_and_notifies_opponent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10)

    async def _fake_series_start(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
            invite_token="token-series",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACTIVE",
            creator_user_id=10,
            opponent_user_id=20,
            current_round=1,
            total_rounds=5,
            series_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
            series_game_number=1,
            series_best_of=3,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    notified: list[int] = []

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback, text, reply_markup
        notified.append(opponent_user_id)

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge
        return "Bob" if user_id == 10 else "Alice"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "create_friend_challenge_best_of_three",
        _fake_series_start,
    )
    monkeypatch.setattr(gameplay, "_notify_opponent", _fake_notify)
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)

    callback = DummyCallback(
        data="friend:series:best3:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_series_best3(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.friend.challenge.series.started"].format(opponent_label="Bob") in (
        response.text or ""
    )
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:next:dddddddd-dddd-dddd-dddd-dddddddddddd" in callbacks
    assert notified == [20]


@pytest.mark.asyncio
async def test_handle_friend_challenge_series_next_creates_game_and_notifies_opponent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10)

    async def _fake_series_next(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            invite_token="token-series-next",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACTIVE",
            creator_user_id=10,
            opponent_user_id=20,
            current_round=1,
            total_rounds=5,
            series_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
            series_game_number=2,
            series_best_of=3,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    async def _fake_series_score(*args, **kwargs):
        return (1, 0, 2, 3)

    notified: list[int] = []

    async def _fake_notify(callback, *, opponent_user_id, text, reply_markup=None):
        del callback, text, reply_markup
        notified.append(opponent_user_id)

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge
        return "Bob" if user_id == 10 else "Alice"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "create_friend_challenge_series_next_game",
        _fake_series_next,
    )
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_series_score_for_user",
        _fake_series_score,
    )
    monkeypatch.setattr(gameplay, "_notify_opponent", _fake_notify)
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)

    callback = DummyCallback(
        data="friend:series:next:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_series_next(callback)

    response = callback.message.answers[0]
    assert "Spiel 2/3" in (response.text or "")
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:next:ffffffff-ffff-ffff-ffff-ffffffffffff" in callbacks
    assert notified == [20]


@pytest.mark.asyncio
async def test_handle_friend_challenge_next_expired_shows_expired_message(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=17, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_start_round(*args, **kwargs):
        raise FriendChallengeExpiredError()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService, "start_friend_challenge_round", _fake_start_round
    )

    callback = DummyCallback(
        data="friend:next:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=17),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_next(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.expired"]


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

    assert any(
        call.text == TEXTS_DE["msg.game.daily.finished"] for call in callback.message.answers
    )


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


@pytest.mark.asyncio
async def test_handle_friend_challenge_share_result_sends_share_url_and_emits_event(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        return FriendChallengeSnapshot(
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
        )

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge
        return "Bob" if user_id == 10 else "Alice"

    emitted: list[str] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(kwargs["event_type"])

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)

    callback = DummyCallback(
        data="friend:share:result:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(bot=DummyBot(username="proofbot")),
    )
    await gameplay.handle_friend_challenge_share_result(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.friend.challenge.proof.share.ready"] in (response.text or "")
    urls = [
        button.url
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.url
    ]
    assert len(urls) == 1
    assert "https://t.me/share/url" in (urls[0] or "")
    assert "https%3A%2F%2Ft.me%2Fproofbot" in (urls[0] or "")
    assert emitted == ["friend_challenge_proof_card_share_clicked"]
