from __future__ import annotations

from datetime import UTC, datetime

from app.workers.tasks.daily_cup_match_results import _build_result_text


def test_build_result_text_for_non_final_round_mentions_next_round_start() -> None:
    text = _build_result_text(
        round_no=2,
        rounds_total=3,
        my_points=4,
        opponent_points=3,
        place=2,
        total_players=8,
        total_score="2.5",
        next_round_deadline=datetime(2026, 3, 3, 19, 0, tzinfo=UTC),
    )

    assert "Runde 3 startet um" in text


def test_build_result_text_for_final_round_mentions_final_evaluation() -> None:
    text = _build_result_text(
        round_no=3,
        rounds_total=3,
        my_points=4,
        opponent_points=2,
        place=1,
        total_players=8,
        total_score="3",
        next_round_deadline=None,
    )

    assert "Finale Auswertung läuft" in text
    assert "startet um" not in text
