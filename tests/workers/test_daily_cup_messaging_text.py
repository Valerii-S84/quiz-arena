from __future__ import annotations

from app.workers.tasks.daily_cup_messaging_text import (
    build_completed_text,
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


def test_build_round_text_includes_bye_autowin_hint() -> None:
    text = build_round_text(
        round_no=2,
        deadline_text="03.03 20:00",
        opponent_label=None,
        standings_lines=["1. 🥇 Ich (Du) - 2 Pkt", "2. 🥈 Max - 1 Pkt"],
    )

    assert "Gegner: Freilos" in text
    assert "Auto-Sieg" in text


def test_build_completed_text_includes_top_3_and_personal_result() -> None:
    text = build_completed_text(
        place=2,
        my_points="2.5",
        standings_lines=["1. 🥇 Lea - 3 Pkt", "2. 🥈 Ich (Du) - 2.5 Pkt", "3. 🥉 Max - 2 Pkt"],
    )

    assert "Daily Arena Cup — Abgeschlossen!" in text
    assert "🥇 1. 🥇 Lea - 3 Pkt" in text
    assert "Platz 2 · 2.5 Punkte" in text
