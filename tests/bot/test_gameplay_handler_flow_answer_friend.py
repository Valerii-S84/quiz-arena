from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from app.game.sessions.types import AnswerSessionResult, FriendChallengeSnapshot
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage, DummySessionLocal


@pytest.fixture(autouse=True)
def _patch_referral_prompt(monkeypatch):
    async def _fake_reserve_post_game_prompt(session, *, user_id: int, now_utc):
        del session, user_id, now_utc
        return False

    async def _fake_emit(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(
        gameplay.ReferralService,
        "reserve_post_game_prompt",
        _fake_reserve_post_game_prompt,
    )
    monkeypatch.setattr(gameplay, "emit_analytics_event", _fake_emit)


@pytest.mark.asyncio
async def test_handle_answer_friend_challenge_completion_sends_proof_card_with_share_button(
    monkeypatch,
) -> None:
    monkeypatch.setattr(gameplay, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=10, free_energy=10, paid_energy=0, current_streak=0)

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

    queued_challenges: list[str] = []

    def _fake_enqueue(*, challenge_id: str) -> None:
        queued_challenges.append(challenge_id)

    monkeypatch.setattr(gameplay.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(gameplay.GameSessionService, "submit_answer", _fake_submit_answer)
    monkeypatch.setattr(gameplay, "_resolve_opponent_label", _fake_resolve_label)
    monkeypatch.setattr(gameplay, "_notify_opponent", _fake_notify)
    monkeypatch.setattr(gameplay.gameplay_proof_cards, "enqueue_duel_proof_cards", _fake_enqueue)

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
    assert "🎉 Gewonnen!" in (finish_call.text or "")
    keyboard = finish_call.kwargs["reply_markup"]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == [
        "friend:rematch:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "arena:list",
    ]
    assert queued_challenges == ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
