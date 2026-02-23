from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.errors import FriendChallengeExpiredError
from app.game.sessions.types import FriendChallengeSnapshot
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage, DummySessionLocal


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
