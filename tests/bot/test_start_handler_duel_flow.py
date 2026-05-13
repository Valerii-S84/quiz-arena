from __future__ import annotations

from dataclasses import replace

from tests.bot.start_handler_flow_support import (
    TEXTS_DE,
    UUID,
    DummySessionLocal,
    FriendChallengeExpiredError,
    FriendChallengeJoinResult,
    FriendChallengeRoundStartResult,
    FriendChallengeSnapshot,
    SessionQuestionView,
    SimpleNamespace,
    StartSessionResult,
    _StartMessage,
)
from tests.bot.start_handler_flow_support import (  # noqa: F401
    _stub_start_runtime as _stub_start_runtime,
)
from tests.bot.start_handler_flow_support import pytest, start

pytestmark = pytest.mark.usefixtures("_stub_start_runtime")


@pytest.mark.asyncio
async def test_handle_start_duel_payload_joins_and_shows_challenge_immediately(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        assert start_payload == "duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        return SimpleNamespace(user_id=9, free_energy=10, paid_energy=1, current_streak=1)

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
    monkeypatch.setattr(
        start.start_flow,
        "FRIEND_CHALLENGE_RENDERERS",
        replace(
            start.start_flow.FRIEND_CHALLENGE_RENDERERS,
            resolve_opponent_label=_fake_resolve_label,
        ),
    )

    message = _StartMessage(
        text="/start duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert len(message.answers) == 2
    assert TEXTS_DE["msg.friend.challenge.joined"] in (message.answers[0].text or "")
    assert message.answers[1].kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_handle_start_duel_payload_expired_returns_expired_message(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        assert start_payload == "duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        return SimpleNamespace(user_id=9, free_energy=10, paid_energy=0, current_streak=1)

    async def _fake_join_by_id(*args, **kwargs):
        del args, kwargs
        raise FriendChallengeExpiredError()

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.GameSessionService, "join_friend_challenge_by_id", _fake_join_by_id)

    message = _StartMessage(
        text="/start duel_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=1, username="alice", first_name="Alice", language_code="de"),
    )
    await start.handle_start(message)

    assert message.answers[0].text == TEXTS_DE["msg.friend.challenge.expired"]


@pytest.mark.asyncio
async def test_handle_start_invalid_legacy_duel_payload_falls_back_to_home(monkeypatch) -> None:
    monkeypatch.setattr(start, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user, start_payload=None):
        assert start_payload == "duel_bad"
        return SimpleNamespace(
            user_id=8,
            free_energy=8,
            paid_energy=3,
            current_streak=4,
            best_streak=9,
            global_best_streak=27,
        )

    async def _fake_offer(*args, **kwargs):
        del args, kwargs
        return None

    async def _unexpected_join(*args, **kwargs):
        del args, kwargs
        pytest.fail("invalid legacy duel payload must not attempt to join a challenge")

    monkeypatch.setattr(start.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(start.OfferService, "evaluate_and_log_offer", _fake_offer)
    monkeypatch.setattr(start.GameSessionService, "join_friend_challenge_by_id", _unexpected_join)

    message = _StartMessage(
        text="/start duel_bad",
        from_user=SimpleNamespace(id=2, username="bob", first_name="Bob", language_code="de"),
    )
    await start.handle_start(message)

    assert len(message.answers) == 1
    assert "Serie: 4 | Beste: 9 | 🏆 Rekord: 27" in (message.answers[0].text or "")
