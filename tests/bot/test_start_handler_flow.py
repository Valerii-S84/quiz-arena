from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import start
from app.bot.texts.de import TEXTS_DE
from app.economy.offers.types import OfferSelection
from app.game.sessions.errors import FriendChallengeExpiredError, FriendChallengeNotFoundError
from app.game.sessions.types import SessionQuestionView, StartSessionResult
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


def test_extract_start_payload() -> None:
    assert start._extract_start_payload("/start ref_ABC123") == "ref_ABC123"
    assert start._extract_start_payload("/start") is None
    assert start._extract_start_payload("not-start") is None


def test_extract_friend_challenge_token() -> None:
    token = "fc_0123456789abcdef0123456789abcdef"
    assert start._extract_friend_challenge_token(token) == "0123456789abcdef0123456789abcdef"
    assert start._extract_friend_challenge_token("fc_invalid") is None
    assert start._extract_friend_challenge_token(None) is None


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
    monkeypatch.setattr(start.GameSessionService, "join_friend_challenge_by_token", _fake_join_friend_challenge)

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
    monkeypatch.setattr(start.GameSessionService, "join_friend_challenge_by_token", _fake_join_friend_challenge)

    message = _StartMessage(
        text="/start fc_0123456789abcdef0123456789abcdef",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert message.answers[0].text == TEXTS_DE["msg.friend.challenge.expired"]


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
