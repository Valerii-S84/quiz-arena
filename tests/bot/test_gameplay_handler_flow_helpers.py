from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import gameplay
from app.bot.texts.de import TEXTS_DE
from tests.bot.gameplay_flow_fixtures import _challenge_snapshot, _start_result
from tests.bot.helpers import DummyCallback, DummyMessage


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
