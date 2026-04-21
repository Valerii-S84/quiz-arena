from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeExpiredError
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage, DummySessionLocal


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
async def test_handle_friend_challenge_share_result_sends_inline_share_and_emits_event(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="token",
            challenge_type="DIRECT",
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
    enqueued: list[tuple[str, int | None]] = []

    async def _fake_emit(*args, **kwargs):
        emitted.append(kwargs["event_type"])

    def _fake_enqueue(*, challenge_id: str, user_id: int | None = None) -> None:
        enqueued.append((challenge_id, user_id))

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)
    monkeypatch.setattr(gameplay.gameplay_proof_cards, "enqueue_duel_proof_cards", _fake_enqueue)

    callback = DummyCallback(
        data="friend:share:result:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(bot=DummyBot(username="proofbot")),
    )
    await gameplay.handle_friend_challenge_share_result(callback)

    response = callback.message.answers[0]
    assert TEXTS_DE["msg.friend.challenge.proof.share.ready"] in (response.text or "")
    inline_queries = [
        button.switch_inline_query
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.switch_inline_query
    ]
    assert inline_queries == ["proof:duel:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
    assert emitted == ["duel_share_clicked"]
    assert enqueued == [("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", 10)]


@pytest.mark.asyncio
async def test_handle_friend_challenge_onboarding_info_shows_info_screen(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="token",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACCEPTED",
            creator_user_id=20,
            opponent_user_id=10,
            current_round=1,
            total_rounds=5,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )

    callback = DummyCallback(
        data="friend:onboarding:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_onboarding_info(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.info"]
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == ["friend:onboarding:show:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]


@pytest.mark.asyncio
async def test_handle_friend_challenge_onboarding_show_rebuilds_play_cta(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="token",
            challenge_type="DIRECT",
            mode_code="QUICK_MIX_A1A2",
            access_type="FREE",
            status="ACCEPTED",
            creator_user_id=20,
            opponent_user_id=10,
            current_round=1,
            total_rounds=5,
            creator_score=0,
            opponent_score=0,
            winner_user_id=None,
        )

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge, user_id
        return "Anna"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)

    callback = DummyCallback(
        data="friend:onboarding:show:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_onboarding_show(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.onboarding"].format(
        challenger_name="Anna"
    )
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == [
        "friend:next:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "friend:onboarding:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    ]


@pytest.mark.asyncio
async def test_handle_friend_challenge_finished_show_rebuilds_actions(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="token",
            challenge_type="DIRECT",
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
        del challenge, user_id
        return "Bob"

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)

    callback = DummyCallback(
        data="friend:finished:show:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_finished_show(callback)

    response = callback.message.answers[0]
    assert "Duell Score: Du 4 | Bob 2." in (response.text or "")
    assert "Sieger: Du." in (response.text or "")
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "daily_challenge" in callbacks
    assert "friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "friend:finished:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "home:open" in callbacks


@pytest.mark.asyncio
async def test_handle_friend_challenge_finished_info_shows_info_screen(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        return FriendChallengeSnapshot(
            challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            invite_token="token",
            challenge_type="DIRECT",
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

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )

    callback = DummyCallback(
        data="friend:finished:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_finished_info(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.info"]
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == ["friend:finished:show:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]


@pytest.mark.asyncio
async def test_handle_friend_challenge_onboarding_info_invalid_shows_home(monkeypatch) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        raise FriendChallengeAccessError()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )

    callback = DummyCallback(
        data="friend:onboarding:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_onboarding_info(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.invalid"]
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == [
        "daily_challenge",
        "friend:challenge:create",
        "play",
        "mode:ARTIKEL_SPRINT",
        "shop:open",
    ]


@pytest.mark.asyncio
async def test_handle_friend_challenge_onboarding_info_expired_shows_finished_keyboard(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=10, free_energy=20, paid_energy=0, current_streak=0)

    async def _fake_get_snapshot(*args, **kwargs):
        raise FriendChallengeExpiredError()

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        gameplay.GameSessionService,
        "get_friend_challenge_snapshot_for_user",
        _fake_get_snapshot,
    )

    callback = DummyCallback(
        data="friend:onboarding:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    await gameplay.handle_friend_challenge_onboarding_info(callback)

    response = callback.message.answers[0]
    assert response.text == TEXTS_DE["msg.friend.challenge.expired"]
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "daily_challenge" in callbacks
    assert "friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "friend:finished:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
    assert "home:open" in callbacks


@pytest.mark.asyncio
async def test_handle_friend_challenge_onboarding_info_invalid_payload_answers_system_error() -> (
    None
):
    callback = DummyCallback(
        data="friend:onboarding:info:not-a-uuid",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )

    await gameplay.handle_friend_challenge_onboarding_info(callback)

    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_friend_challenge_onboarding_info_missing_message_answers_system_error() -> (
    None
):
    callback = DummyCallback(
        data="friend:onboarding:info:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(),
    )
    setattr(callback, "message", None)

    await gameplay.handle_friend_challenge_onboarding_info(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]
