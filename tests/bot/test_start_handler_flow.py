from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.bot.handlers import start
from app.bot.texts.de import TEXTS_DE
from app.economy.offers.types import OfferSelection
from app.game.sessions.errors import FriendChallengeExpiredError, FriendChallengeNotFoundError
from app.game.sessions.types import (
    FriendChallengeJoinResult,
    FriendChallengeRoundStartResult,
    FriendChallengeSnapshot,
    SessionQuestionView,
    StartSessionResult,
)
from tests.bot.helpers import DummyMessage, DummySessionLocal


class _StartMessage(DummyMessage):
    def __init__(
        self,
        *,
        text: str,
        from_user: SimpleNamespace | None,
        message_id: int = 100,
    ) -> None:
        super().__init__()
        self.text = text
        self.from_user = from_user
        self.message_id = message_id


class _StartMessageWithPhotoGuard(_StartMessage):
    def __init__(
        self,
        *,
        text: str,
        from_user: SimpleNamespace | None,
        message_id: int = 100,
    ) -> None:
        super().__init__(text=text, from_user=from_user, message_id=message_id)
        self.photo_calls = 0

    async def answer_photo(self, *args: Any, **kwargs: Any) -> None:
        self.photo_calls += 1
        await super().answer(*args, **kwargs)


def test_extract_start_payload() -> None:
    assert start._extract_start_payload("/start ref_ABC123") == "ref_ABC123"
    assert start._extract_start_payload("/start") is None
    assert start._extract_start_payload("not-start") is None


def test_extract_friend_challenge_token() -> None:
    token = "fc_0123456789abcdef0123456789abcdef"
    assert start._extract_friend_challenge_token(token) == "0123456789abcdef0123456789abcdef"
    assert start._extract_friend_challenge_token("fc_invalid") is None
    assert start._extract_friend_challenge_token(None) is None


def test_extract_duel_challenge_id() -> None:
    duel_payload = "duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert start._extract_duel_challenge_id(duel_payload) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert start._extract_duel_challenge_id("duel_bad") is None
    assert start._extract_duel_challenge_id(None) is None


def test_extract_tournament_invite_code() -> None:
    assert start._extract_tournament_invite_code("tournament_abcdefabcdef") == "abcdefabcdef"
    assert start._extract_tournament_invite_code("tournament_bad") is None
    assert start._extract_tournament_invite_code(None) is None


def test_build_question_text_contains_theme_counter_and_energy() -> None:
    start_result = StartSessionResult(
        session=SessionQuestionView(
            session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            question_id="q-1",
            text="Was passt?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            category="Wortschatz - Alltag",
            question_number=1,
            total_questions=1,
        ),
        energy_free=10,
        energy_paid=0,
        idempotent_replay=False,
    )
    text = start._build_question_text(
        source="MENU",
        snapshot_free_energy=10,
        snapshot_paid_energy=0,
        start_result=start_result,
    )
    assert "⚡" in text
    assert "🔋 Energie:" in text
    assert "📚 Thema:" in text
    assert "❓ Frage 1/1" in text


@pytest.mark.asyncio
async def test_handle_start_rejects_missing_user() -> None:
    message = _StartMessage(text="/start", from_user=None)

    await start.handle_start(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.system.error"]


@pytest.mark.asyncio
async def test_handle_start_friend_token_invalid(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=7, free_energy=20, paid_energy=0, current_streak=1)

    async def _fake_join_friend_challenge(*args, **kwargs):
        raise FriendChallengeNotFoundError()

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        start.GameSessionService,
        "join_friend_challenge_by_token",
        _fake_join_friend_challenge,
    )

    message = _StartMessage(
        text="/start fc_0123456789abcdef0123456789abcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert message.answers[0].text == TEXTS_DE["msg.friend.challenge.invalid"]


@pytest.mark.asyncio
async def test_handle_start_friend_token_expired(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=9, free_energy=20, paid_energy=0, current_streak=1)

    async def _fake_join_friend_challenge(*args, **kwargs):
        raise FriendChallengeExpiredError()

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        start.GameSessionService,
        "join_friend_challenge_by_token",
        _fake_join_friend_challenge,
    )

    message = _StartMessage(
        text="/start fc_0123456789abcdef0123456789abcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert message.answers[0].text == TEXTS_DE["msg.friend.challenge.expired"]


@pytest.mark.asyncio
async def test_handle_start_duel_payload_joins_and_shows_challenge_immediately(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        assert start_payload == "duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        return SimpleNamespace(user_id=9, free_energy=20, paid_energy=1, current_streak=1)

    async def _fake_join_by_id(*args, **kwargs):
        return FriendChallengeJoinResult(
            snapshot=FriendChallengeSnapshot(
                challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_token="token",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="ACCEPTED",
                creator_user_id=1,
                opponent_user_id=9,
                current_round=1,
                total_rounds=5,
                creator_score=0,
                opponent_score=0,
                winner_user_id=None,
            ),
            joined_now=True,
        )

    async def _fake_start_round(*args, **kwargs):
        return FriendChallengeRoundStartResult(
            snapshot=FriendChallengeSnapshot(
                challenge_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_token="token",
                challenge_type="DIRECT",
                mode_code="QUICK_MIX_A1A2",
                access_type="FREE",
                status="ACCEPTED",
                creator_user_id=1,
                opponent_user_id=9,
                current_round=1,
                total_rounds=5,
                creator_score=0,
                opponent_score=0,
                winner_user_id=None,
            ),
            start_result=StartSessionResult(
                session=SessionQuestionView(
                    session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                    question_id="q-1",
                    text="Frage?",
                    options=("A", "B", "C", "D"),
                    mode_code="QUICK_MIX_A1A2",
                    source="FRIEND_CHALLENGE",
                    category="Test",
                    question_number=1,
                    total_questions=5,
                ),
                energy_free=20,
                energy_paid=1,
                idempotent_replay=False,
            ),
            waiting_for_opponent=False,
            already_answered_current_round=False,
        )

    async def _fake_notify_creator(*args, **kwargs):
        return None

    async def _fake_resolve_label(*, challenge, user_id):
        del challenge, user_id
        return "Freund"

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.GameSessionService, "join_friend_challenge_by_id", _fake_join_by_id)
    monkeypatch.setattr(start.GameSessionService, "start_friend_challenge_round", _fake_start_round)
    monkeypatch.setattr(start.start_flow, "_notify_creator_about_join", _fake_notify_creator)
    monkeypatch.setattr(start.start_flow, "_resolve_opponent_label", _fake_resolve_label)

    message = _StartMessage(
        text="/start duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert len(message.answers) == 2
    assert TEXTS_DE["msg.friend.challenge.joined"] in (message.answers[0].text or "")
    assert message.answers[1].kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_handle_start_tournament_payload_shows_lobby_and_join_button(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        assert start_payload == "tournament_abcdefabcdef"
        return SimpleNamespace(user_id=9, free_energy=20, paid_energy=1, current_streak=1)

    async def _fake_lobby_by_code(*args, **kwargs):
        return SimpleNamespace(
            tournament=SimpleNamespace(
                tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                invite_code="abcdefabcdef",
                name="Freunde",
                format="QUICK_5",
                max_participants=8,
                current_round=0,
                status="REGISTRATION",
            ),
            participants=(
                SimpleNamespace(user_id=11, score=0),
                SimpleNamespace(user_id=12, score=0),
            ),
            viewer_joined=False,
            can_start=False,
            viewer_current_match_challenge_id=None,
        )

    async def _fake_list_by_ids(*args, **kwargs):
        return [
            SimpleNamespace(id=11, username="max", first_name="Max"),
            SimpleNamespace(id=12, username="anna", first_name="Anna"),
        ]

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(
        start.start_flow.TournamentServiceFacade,
        "get_private_tournament_lobby_by_invite_code",
        _fake_lobby_by_code,
    )
    monkeypatch.setattr(start.start_flow.UsersRepo, "list_by_ids", _fake_list_by_ids)

    message = _StartMessage(
        text="/start tournament_abcdefabcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    response = message.answers[0]
    assert "Teilnehmer: 2/8" in (response.text or "")
    callbacks = [
        button.callback_data
        for row in response.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "friend:tournament:join:abcdefabcdef" in callbacks


@pytest.mark.asyncio
async def test_handle_start_sends_home_and_offer_when_available(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=8, free_energy=12, paid_energy=3, current_streak=4)

    async def _fake_offer(*args, **kwargs):
        return OfferSelection(
            impression_id=1,
            offer_code="ENERGY_10",
            trigger_code="TRG_ENERGY_LOW",
            priority=100,
            text_key="msg.offer.energy.low",
            cta_product_codes=("ENERGY_10",),
            idempotent_replay=False,
        )

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)

    message = _StartMessage(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert len(message.answers) == 2
    assert TEXTS_DE["msg.home.title"] in (message.answers[0].text or "")
    assert message.answers[1].text == TEXTS_DE["msg.offer.energy.low"]


@pytest.mark.asyncio
async def test_handle_start_home_menu_does_not_send_photo(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=8, free_energy=12, paid_energy=3, current_streak=4)

    async def _fake_offer(*args, **kwargs):
        return None

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)
    monkeypatch.setattr(
        start.start_flow,
        "get_settings",
        lambda: SimpleNamespace(telegram_home_header_file_id=""),
    )

    message = _StartMessageWithPhotoGuard(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert message.photo_calls == 0


@pytest.mark.asyncio
async def test_handle_start_home_menu_hides_streak_when_zero(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=8, free_energy=12, paid_energy=3, current_streak=0)

    async def _fake_offer(*args, **kwargs):
        return None

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)
    monkeypatch.setattr(
        start.start_flow,
        "get_settings",
        lambda: SimpleNamespace(telegram_home_header_file_id=""),
    )

    message = _StartMessage(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    home_text = message.answers[0].text or ""
    assert "⚡ 12/20 + 3 Bonus" in home_text
    assert "🔥" not in home_text


@pytest.mark.asyncio
async def test_handle_start_home_menu_sends_photo_when_file_id_configured(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        return SimpleNamespace(user_id=8, free_energy=12, paid_energy=3, current_streak=4)

    async def _fake_offer(*args, **kwargs):
        return None

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)
    monkeypatch.setattr(
        start.start_flow,
        "get_settings",
        lambda: SimpleNamespace(telegram_home_header_file_id="AgAC-home-header"),
    )

    message = _StartMessage(
        text="/start",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert len(message.answers) == 1
    assert message.answers[0].kwargs.get("photo") == "AgAC-home-header"
    assert TEXTS_DE["msg.home.title"] in (message.answers[0].text or "")
