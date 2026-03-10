from __future__ import annotations

from datetime import UTC, datetime

from app.workers.tasks.daily_cup_messaging_text import (
    build_completed_text,
    build_next_round_start_text,
    build_round_text,
    build_standings_lines,
)


def test_build_standings_lines_without_tie_break() -> None:
    lines = build_standings_lines(
        standings_user_ids=[101, 202],
        labels={101: "Ich", 202: "Max"},
        points_by_user={101: "3", 202: "2.5"},
        viewer_user_id=101,
    )

    assert lines[0] == "1. 🥇 Ich (Du) - 3 Pkt"
    assert lines[1] == "2. 🥈 Max - 2.5 Pkt"


def test_build_standings_lines_with_tie_break() -> None:
    lines = build_standings_lines(
        standings_user_ids=[101, 202],
        labels={101: "Ich", 202: "Max"},
        points_by_user={101: "3", 202: "2.5"},
        viewer_user_id=101,
        tie_breaks_by_user={101: "9", 202: "4.5"},
    )

    assert lines[0] == "1. 🥇 Ich (Du) - 3 Pkt · TB 9"
    assert lines[1] == "2. 🥈 Max - 2.5 Pkt · TB 4.5"


def test_build_round_text_uses_arena_bot_label_for_self_match() -> None:
    text = build_round_text(
        round_no=2,
        rounds_total=3,
        deadline_text="03.03 20:00",
        opponent_label=None,
        standings_lines=["1. 🥇 Ich (Du) - 2 Pkt", "2. 🥈 Max - 1 Pkt"],
    )

    assert "⚔️ Runde 2/3 gestartet" in text
    assert "Gegner: Arena Bot" in text
    assert "Auto-Sieg" not in text


def test_build_next_round_start_text_uses_actual_db_start_time() -> None:
    text = build_next_round_start_text(
        round_no=3,
        tournament_start=datetime(2026, 3, 3, 17, 0, tzinfo=UTC),
        round_start_time=datetime(2026, 3, 3, 18, 0, tzinfo=UTC),
    )

    assert text == "um 19:00"


def test_build_next_round_start_text_uses_delayed_db_start_time() -> None:
    text = build_next_round_start_text(
        round_no=3,
        tournament_start=datetime(2026, 3, 3, 17, 0, tzinfo=UTC),
        round_start_time=datetime(2026, 3, 3, 18, 17, tzinfo=UTC),
    )

    assert text == "um 19:17"


def test_build_next_round_start_text_falls_back_to_planned_slot() -> None:
    text = build_next_round_start_text(
        round_no=4,
        tournament_start=datetime(2026, 3, 3, 17, 0, tzinfo=UTC),
        round_start_time=None,
    )

    assert text == "voraussichtlich 19:30"


def test_build_completed_text_includes_top_3_and_personal_result() -> None:
    text = build_completed_text(
        place=2,
        my_points="2.5",
        standings_lines=["1. 🥇 Lea - 3 Pkt", "2. 🥈 Ich (Du) - 2.5 Pkt", "3. 🥉 Max - 2 Pkt"],
    )

    assert "Daily Arena Cup — Abgeschlossen!" in text
    assert "🥇 1. 🥇 Lea - 3 Pkt" in text
    assert "Platz 2 · 2.5 Punkte" in text
