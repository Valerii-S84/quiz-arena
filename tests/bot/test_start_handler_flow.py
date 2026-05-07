from __future__ import annotations

from tests.bot.start_handler_flow_support import UUID, SessionQuestionView, StartSessionResult
from tests.bot.start_handler_flow_support import (  # noqa: F401
    _stub_start_runtime as _stub_start_runtime,
)
from tests.bot.start_handler_flow_support import pytest, start

pytestmark = pytest.mark.usefixtures("_stub_start_runtime")


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


def test_build_question_text_contains_theme_counter_and_energy() -> None:
    start_result = StartSessionResult(
        session=SessionQuestionView(
            session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            question_id="q-1",
            text="Was passt?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source="MENU",
            category="B2 Wortschatz - Alltag",
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
    assert "📚 Thema: Wortschatz - Alltag" in text
    assert "❓ Frage 1/1" in text
    assert "B2" not in text


@pytest.mark.parametrize("source", ["ARENA_DUEL", "FRIEND_CHALLENGE"])
def test_start_question_text_hides_theme_for_duel_sources(source: str) -> None:
    start_result = StartSessionResult(
        session=SessionQuestionView(
            session_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            question_id="q-1",
            text="Was passt?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source=source,
            category="Artikel - Nominativ",
            question_number=1,
            total_questions=7,
        ),
        energy_free=10,
        energy_paid=0,
        idempotent_replay=False,
    )

    text = start._build_question_text(
        source=source,
        snapshot_free_energy=10,
        snapshot_paid_energy=0,
        start_result=start_result,
    )

    assert "📚 Thema:" not in text
    assert "Artikel - Nominativ" not in text
    assert "❓ Frage 1/7" in text
