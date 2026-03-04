from __future__ import annotations

from app.game.sessions.service.daily_question_sets import (
    daily_level_window_for_position,
    is_daily_level_allowed_for_position,
)


def test_daily_level_window_matches_expected_sequence() -> None:
    expected_preferred = ("A1", "A1", "A2", "A2", "A2", "B1", "B1")
    observed = tuple(daily_level_window_for_position(position)[0] for position in range(1, 8))
    assert observed == expected_preferred


def test_daily_level_window_caps_allowed_levels_by_position() -> None:
    assert is_daily_level_allowed_for_position(position=1, level="A1") is True
    assert is_daily_level_allowed_for_position(position=1, level="A2") is False
    assert is_daily_level_allowed_for_position(position=5, level="A2") is True
    assert is_daily_level_allowed_for_position(position=5, level="B1") is False
    assert is_daily_level_allowed_for_position(position=6, level="B1") is True
