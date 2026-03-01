from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import friend_answer_completion_flow
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage, DummySessionLocal


@pytest.mark.asyncio
async def test_completed_tournament_match_uses_tournament_keyboard_without_rematch(
    monkeypatch,
) -> None:
    tournament_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    enqueued: list[str] = []

    async def _fake_resolve_tournament_id_for_match(*, session_local, tournament_match_id):
        del session_local, tournament_match_id
        return tournament_id

    def _fake_enqueue_tournament_post_match_updates(*, tournament_id: str) -> None:
        enqueued.append(tournament_id)

    async def _fake_notify_opponent(callback, *, opponent_user_id, text, reply_markup=None):
        del callback, opponent_user_id, text, reply_markup
        return None

    async def _fake_resolve_opponent_label(*, challenge, user_id: int):
        del challenge
        return "Alice" if user_id == 20 else "Bob"

    monkeypatch.setattr(
        friend_answer_completion_flow,
        "resolve_tournament_id_for_match",
        _fake_resolve_tournament_id_for_match,
    )
    monkeypatch.setattr(
        friend_answer_completion_flow,
        "enqueue_tournament_post_match_updates",
        _fake_enqueue_tournament_post_match_updates,
    )

    callback = DummyCallback(
        data="answer:123e4567-e89b-12d3-a456-426614174000:0",
        from_user=SimpleNamespace(id=10),
        message=DummyMessage(bot=DummyBot(username="proofbot")),
    )
    challenge = SimpleNamespace(
        challenge_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        creator_user_id=10,
        opponent_user_id=20,
        creator_score=4,
        opponent_score=2,
        total_rounds=5,
        winner_user_id=10,
        series_id=None,
        series_game_number=1,
        series_best_of=1,
        tournament_match_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    )

    await friend_answer_completion_flow.handle_completed_friend_challenge(
        callback,
        challenge=challenge,
        snapshot_user_id=10,
        opponent_label="Bob",
        opponent_user_id=20,
        now_utc=datetime.now(timezone.utc),
        idempotent_replay=False,
        session_local=DummySessionLocal(),
        game_session_service=SimpleNamespace(),
        resolve_opponent_label=_fake_resolve_opponent_label,
        notify_opponent=_fake_notify_opponent,
        build_friend_score_text=lambda **kwargs: "score",
        build_friend_finish_text=lambda **kwargs: "finish",
        build_public_badge_label=lambda **kwargs: "badge",
        build_friend_proof_card_text=lambda **kwargs: "proof",
        enqueue_friend_challenge_proof_cards=lambda **kwargs: None,
        build_series_progress_text=lambda **kwargs: "series",
    )

    response = callback.message.answers[0]
    assert "✅ Match gespielt!" in (response.text or "")
    buttons = [button for row in response.kwargs["reply_markup"].inline_keyboard for button in row]
    labels = [button.text for button in buttons]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "📊 Turnier-Tabelle" in labels
    assert "🔄 Revanche" not in labels
    assert f"friend:tournament:view:{tournament_id}" in callbacks
    assert enqueued == [tournament_id]
