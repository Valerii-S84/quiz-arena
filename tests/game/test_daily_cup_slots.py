from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.game.tournaments.daily_cup_slots import get_round_deadline


def test_get_round_deadline_returns_all_four_fixed_berlin_slots() -> None:
    berlin = ZoneInfo("Europe/Berlin")
    tournament_start = datetime(2026, 3, 1, 18, 0, tzinfo=berlin)

    assert get_round_deadline(round_number=1, tournament_start=tournament_start) == datetime(
        2026, 3, 1, 18, 30, tzinfo=berlin
    )
    assert get_round_deadline(round_number=2, tournament_start=tournament_start) == datetime(
        2026, 3, 1, 19, 0, tzinfo=berlin
    )
    assert get_round_deadline(round_number=3, tournament_start=tournament_start) == datetime(
        2026, 3, 1, 19, 30, tzinfo=berlin
    )
    assert get_round_deadline(round_number=4, tournament_start=tournament_start) == datetime(
        2026, 3, 1, 20, 0, tzinfo=berlin
    )
