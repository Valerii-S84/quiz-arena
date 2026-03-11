from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.handlers import gameplay, gameplay_views_question
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
    start_result = _start_result()
    start_result.session.category = "A1 Artikel - Nominativ"
    text = gameplay._build_question_text(
        source="MENU",
        snapshot_free_energy=18,
        snapshot_paid_energy=2,
        start_result=start_result,
    )
    assert "⚡" in text
    assert "🔋 Energie:" in text
    assert "📚 Thema: Artikel - Nominativ" in text
    assert "❓ Frage 3/12" in text
    assert "A1" not in text


@pytest.mark.parametrize(
    ("mode_code", "expected_label", "legacy_labels"),
    [
        (
            "ARTIKEL_SPRINT",
            "Artikel-Training",
            ("ARTIKEL SPRINT", "Artikel Sprint"),
        ),
        (
            "QUICK_MIX_A1A2",
            "Schnell-Runde",
            ("QUICK MIX", "Quick Mix"),
        ),
    ],
)
def test_build_question_text_uses_unified_mode_labels(
    mode_code: str,
    expected_label: str,
    legacy_labels: tuple[str, str],
) -> None:
    start_result = _start_result()
    start_result.session.mode_code = mode_code

    text = gameplay._build_question_text(
        source="MENU",
        snapshot_free_energy=18,
        snapshot_paid_energy=2,
        start_result=start_result,
    )

    assert f"<b>⚡ {expected_label}</b>" in text
    for legacy_label in legacy_labels:
        assert legacy_label not in text


def test_build_question_text_reads_mode_label_from_presentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_result = _start_result()
    start_result.session.mode_code = "ARTIKEL_SPRINT"

    monkeypatch.setattr(
        gameplay_views_question,
        "display_mode_label",
        lambda mode_code: f"presentation:{mode_code}",
    )

    text = gameplay._build_question_text(
        source="MENU",
        snapshot_free_energy=18,
        snapshot_paid_energy=2,
        start_result=start_result,
    )

    assert "<b>⚡ presentation:ARTIKEL_SPRINT</b>" in text


def test_build_question_text_uses_daily_arena_cup_header_override() -> None:
    start_result = _start_result()
    start_result.session.header_mode_label_override = "Daily Arena Cup"

    text = gameplay._build_question_text(
        source="FRIEND_CHALLENGE",
        snapshot_free_energy=18,
        snapshot_paid_energy=2,
        start_result=start_result,
    )

    assert "<b>⚡ Daily Arena Cup</b>" in text


def test_build_friend_plan_text_hides_level_mix() -> None:
    text = gameplay._build_friend_plan_text(total_rounds=12)

    assert text == "12 Fragen Mix. Keine Energie-Kosten."
    assert "A1" not in text
    assert "A2" not in text
    assert "B1" not in text


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
async def test_build_friend_invite_link_uses_public_bot_username() -> None:
    callback = DummyCallback(
        data="x",
        from_user=SimpleNamespace(id=1),
        message=DummyMessage(),
    )
    invite_link = await gameplay._build_friend_invite_link(
        callback,
        challenge_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    assert invite_link == (
        "https://t.me/Deine_Deutsch_Quiz_bot?start=duel_" "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )


@pytest.mark.asyncio
async def test_build_friend_result_share_url_uses_public_bot_link() -> None:
    callback = DummyCallback(
        data="x",
        from_user=SimpleNamespace(id=1),
        message=DummyMessage(),
    )
    share_url = await gameplay._build_friend_result_share_url(
        callback,
        proof_card_text="proof card",
    )
    assert share_url is not None
    assert "https%3A%2F%2Ft.me%2FDeine_Deutsch_Quiz_bot" in share_url
