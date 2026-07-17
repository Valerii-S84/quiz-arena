from __future__ import annotations

import pytest

from app.game.tournaments import lifecycle, lifecycle_state
from app.game.tournaments.constants import (
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from tests.game.tournaments_unit_support import (
    NOW_UTC,
    TournamentSession,
    async_return,
    match_row,
    tournament_row,
)


@pytest.mark.asyncio
async def test_close_expired_registration_only_cancels_registration() -> None:
    active = tournament_row(status="ROUND_1")
    registration = tournament_row(status=TOURNAMENT_STATUS_REGISTRATION)

    assert not await lifecycle.close_expired_registration(TournamentSession(), tournament=active)
    assert await lifecycle.close_expired_registration(TournamentSession(), tournament=registration)
    assert registration.status == "CANCELED"


def test_lifecycle_state_helpers_cover_daily_and_private_deadlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    daily = tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA, registration_deadline=NOW_UTC)
    private = tournament_row()

    lifecycle_state.mark_round_started(
        tournament=daily,
        round_no=1,
        deadline=NOW_UTC,
        now_utc=NOW_UTC,
    )
    assert daily.status == "ROUND_1"
    assert daily.round_start_time == NOW_UTC
    lifecycle_state.mark_tournament_completed(tournament=daily)
    assert daily.round_deadline is None

    monkeypatch.setattr(
        lifecycle_state,
        "get_round_deadline",
        lambda **_kwargs: NOW_UTC,
    )
    assert (
        lifecycle_state.resolve_deadline_for_tournament(
            tournament=daily,
            next_round=2,
            now_utc=NOW_UTC,
            round_duration_hours=2,
        )
        == NOW_UTC
    )
    assert (
        lifecycle_state.resolve_deadline_for_tournament(
            tournament=private,
            next_round=2,
            now_utc=NOW_UTC,
            round_duration_hours=2,
        )
        > NOW_UTC
    )

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.workers.tasks.daily_cup_messaging",
        type(
            "M",
            (),
            {"enqueue_daily_cup_round_messaging": lambda tournament_id: sent.append(tournament_id)},
        ),
    )
    lifecycle_state.enqueue_daily_cup_round_messaging(tournament_id=daily.id)
    assert sent == [str(daily.id)]


@pytest.mark.asyncio
async def test_settle_round_and_advance_returns_early_when_pending_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(status="ROUND_1", current_round=1)
    calls: list[str] = []

    async def _lock(*_args, **_kwargs) -> None:
        calls.append("lock")

    async def _list_matches(*_args, **_kwargs):
        calls.append("matches")
        return [match_row(status="PENDING")]

    monkeypatch.setattr(
        lifecycle.TournamentMatchesRepo,
        "list_by_tournament_round_for_update",
        _list_matches,
    )
    monkeypatch.setattr(lifecycle, "settle_pending_match_from_duel", async_return(False))
    monkeypatch.setattr(lifecycle, "lock_standings_phase_transition", _lock)

    result = await lifecycle.settle_round_and_advance(
        TournamentSession(),
        tournament=tournament,
        now_utc=NOW_UTC,
    )

    assert result == {
        "matches_settled": 0,
        "matches_created": 0,
        "round_started": 0,
        "tournament_completed": 0,
    }
    assert calls == ["lock", "matches"]


@pytest.mark.asyncio
async def test_check_and_advance_round_guards_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lifecycle.TournamentsRepo, "get_by_id_for_update", async_return(None))
    assert (
        await lifecycle.check_and_advance_round(
            TournamentSession(),
            tournament_id=tournament_row().id,
            now_utc=NOW_UTC,
        )
        == lifecycle_state.build_transition_result()
    )

    tournament = tournament_row(status="ROUND_1", current_round=1)
    monkeypatch.setattr(lifecycle.TournamentsRepo, "get_by_id_for_update", async_return(tournament))
    monkeypatch.setattr(
        lifecycle.TournamentMatchesRepo,
        "count_pending_for_tournament_round",
        async_return(1),
    )
    assert (
        await lifecycle.check_and_advance_round(
            TournamentSession(),
            tournament_id=tournament.id,
            now_utc=NOW_UTC,
        )
        == lifecycle_state.build_transition_result()
    )

    monkeypatch.setattr(
        lifecycle.TournamentMatchesRepo,
        "count_pending_for_tournament_round",
        async_return(0),
    )
    monkeypatch.setattr(lifecycle, "settle_round_and_advance", async_return({"round_started": 1}))
    assert await lifecycle.check_and_advance_round(
        TournamentSession(),
        tournament_id=tournament.id,
        now_utc=NOW_UTC,
    ) == {"round_started": 1}
