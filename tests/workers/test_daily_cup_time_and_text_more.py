from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.workers.tasks import daily_cup_messaging_text as messaging_text
from app.workers.tasks import daily_cup_proof_cards_text as card_text
from app.workers.tasks import daily_cup_time


def test_daily_cup_window_uses_berlin_business_date_and_utc_bounds() -> None:
    window = daily_cup_time.get_daily_cup_window(now_utc=datetime(2026, 5, 10, 10, 30, tzinfo=UTC))

    assert window.berlin_date.isoformat() == "2026-05-10"
    assert window.open_at_utc.tzinfo is UTC
    assert window.close_at_utc.tzinfo is UTC
    assert (
        daily_cup_time.format_close_time_local(close_at_utc=window.close_at_utc)
        == f"{daily_cup_time.DAILY_CUP_CLOSE_HOUR:02d}:{daily_cup_time.DAILY_CUP_CLOSE_MINUTE:02d}"
    )


def test_daily_cup_proof_card_text_helpers_cover_fallbacks() -> None:
    assert card_text.format_user_label(username="  lea ", first_name="Max") == "@lea"
    assert card_text.format_user_label(username=" ", first_name="  Max  ") == "Max"
    assert card_text.format_user_label(username=None, first_name=" ") == "Spieler"
    assert card_text.format_points(Decimal("4.000")) == "4"
    assert card_text.format_points(Decimal("4.250")) == "4.25"
    assert "Platz #1" in card_text.build_caption(place=1, points="4.25")


def test_daily_cup_completed_text_pads_missing_top_three() -> None:
    text = messaging_text.build_completed_text(
        place=1,
        my_points="3",
        standings_lines=["1. 🥇 Ich (Du) - 3 Pkt"],
    )

    assert "—" in text
    assert "Platz 1 · 3 Punkte" in text


def test_daily_cup_standings_fallbacks_and_round_text_opponent() -> None:
    lines = messaging_text.build_standings_lines(
        standings_user_ids=[1, 2, 3, 4],
        labels={},
        points_by_user={},
        viewer_user_id=4,
        tie_breaks_by_user={1: "8"},
    )

    assert lines[0] == "1. 🥇 Spieler - 0 Pkt · TB 8"
    assert lines[3] == "4.   Spieler (Du) - 0 Pkt · TB 0"

    round_text = messaging_text.build_round_text(
        round_no=3,
        rounds_total=4,
        deadline_text="18:30",
        opponent_label="Lea",
        standings_lines=lines[:2],
    )
    assert "⚔️ Runde 3/4 gestartet" in round_text
    assert "Gegner: Lea" in round_text
