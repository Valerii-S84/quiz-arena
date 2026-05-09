from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from app.game.tournaments import constants, internal
from app.game.tournaments.errors import TournamentError
from tests.game.tournaments_unit_support import (
    NOW_UTC,
    async_return,
    participant_row,
    tournament_row,
)


def test_tournament_constants_cover_round_and_format_branches() -> None:
    assert constants.daily_cup_max_rounds_for_participants(participants_total=20) == 3
    assert constants.daily_cup_max_rounds_for_participants(participants_total=21) == 4
    assert constants.rounds_for_tournament_format(format_code="QUICK_5") == 5
    assert constants.rounds_for_tournament_format(format_code="QUICK_12") == 12
    assert constants.status_for_round(round_no=1) == "ROUND_1"
    assert constants.status_for_round(round_no=2) == "ROUND_2"
    assert constants.status_for_round(round_no=3) == "ROUND_3"
    assert constants.status_for_round(round_no=4) == "ROUND_4"

    with pytest.raises(ValueError):
        constants.rounds_for_tournament_format(format_code="bad")
    with pytest.raises(ValueError):
        constants.status_for_round(round_no=5)


def test_internal_deadlines_and_participant_conversion() -> None:
    assert internal.resolve_registration_deadline(
        now_utc=NOW_UTC,
        registration_deadline=NOW_UTC + timedelta(hours=2),
    ) == NOW_UTC + timedelta(hours=2)
    assert (
        internal.resolve_registration_deadline(
            now_utc=NOW_UTC,
            registration_deadline=None,
        )
        > NOW_UTC
    )
    assert internal.resolve_round_deadline(now_utc=NOW_UTC, round_duration_hours=0) == (
        NOW_UTC + timedelta(hours=1)
    )

    tournament = tournament_row()
    participant = participant_row(tournament_id=tournament.id, user_id=11, score="2.5")
    converted = internal.participants_to_swiss([participant])
    assert converted[0].score == Decimal("2.5")
    assert converted[0].tie_break == Decimal("2.5")


@pytest.mark.asyncio
async def test_generate_invite_code_retries_and_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    async def _existing_then_empty(_session, _code):
        calls["count"] += 1
        return object() if calls["count"] == 1 else None

    monkeypatch.setattr(internal.TournamentsRepo, "get_by_invite_code", _existing_then_empty)
    session = cast(Any, object())

    assert await internal.generate_invite_code(session) != ""
    assert calls["count"] == 2

    monkeypatch.setattr(internal.TournamentsRepo, "get_by_invite_code", async_return(object()))
    with pytest.raises(TournamentError):
        await internal.generate_invite_code(session)
