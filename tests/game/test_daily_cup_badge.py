from __future__ import annotations

from datetime import datetime, timezone

from app.game.tournaments.daily_cup_badge import _has_required_streak


def test_has_required_streak_accepts_five_consecutive_days() -> None:
    joined_at_values = [
        datetime(2026, 2, 1, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 2, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 3, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 4, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 5, 19, 0, tzinfo=timezone.utc),
    ]
    assert _has_required_streak(joined_at_values=joined_at_values, timezone_name="Europe/Berlin")


def test_has_required_streak_rejects_non_consecutive_days() -> None:
    joined_at_values = [
        datetime(2026, 2, 1, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 2, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 4, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 5, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 6, 19, 0, tzinfo=timezone.utc),
    ]
    assert not _has_required_streak(
        joined_at_values=joined_at_values,
        timezone_name="Europe/Berlin",
    )
