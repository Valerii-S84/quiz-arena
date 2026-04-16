from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.game.tournaments import daily_cup_user_status
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED, TOURNAMENT_TYPE_DAILY_ARENA
from app.game.tournaments.daily_cup_user_status import DailyCupUserStatus
from tests.game.daily_arena_golden_extended_support import (
    DailyArenaExtendedSession,
    arena_tournament,
)
from tests.game.daily_arena_golden_support import async_return, patch_status_window


@pytest.mark.parametrize(
    ("raw_value", "defaults", "expected"),
    [
        ("bad", (16, 0), (16, 0)),
        ("25:99", (18, 0), (18, 0)),
        ("09:45", (0, 0), (9, 45)),
    ],
    ids=["broken", "out_of_range", "valid"],
)
def test_daily_arena_status_time_helpers_keep_current_parsing_rules(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    defaults: tuple[int, int],
    expected: tuple[int, int],
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    monkeypatch.setattr(daily_cup_user_status.settings, "daily_cup_timezone", "Europe/Berlin")
    monkeypatch.setattr(
        daily_cup_user_status,
        "DAILY_CUP_TOURNAMENT_TYPE",
        TOURNAMENT_TYPE_DAILY_ARENA,
    )
    monkeypatch.setenv("DAILY_CUP_INVITE_TIME", "broken")
    monkeypatch.setenv("DAILY_CUP_CLOSE_TIME", "25:99")

    assert (
        daily_cup_user_status._parse_hhmm(
            raw_value, default_hour=defaults[0], default_minute=defaults[1]
        )
        == expected
    )

    now_utc = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    anchor = daily_cup_user_status._local_daily_cup_anchor(now_utc=now_utc, hour=16, minute=0)

    assert anchor.hour == 16
    assert anchor.minute == 0
    assert anchor.tzinfo is not None
    assert daily_cup_user_status._invite_open_at_utc(now_utc=now_utc) == datetime(
        2026, 3, 1, 15, 0, tzinfo=UTC
    )
    assert daily_cup_user_status._close_at_utc(now_utc=now_utc) == datetime(
        2026, 3, 1, 17, 0, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_daily_arena_status_returns_no_tournament_before_invite_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    monkeypatch.setattr(
        daily_cup_user_status,
        "_invite_open_at_utc",
        lambda *, now_utc: now_utc + timedelta(minutes=1),
    )

    async def _unexpected_lookup(*args, **kwargs):
        del args, kwargs
        pytest.fail("unexpected tournament lookup before invite window")

    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        _unexpected_lookup,
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        DailyArenaExtendedSession(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 16, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.NO_TOURNAMENT
    assert snapshot.tournament is None


@pytest.mark.asyncio
async def test_daily_arena_status_returns_not_participant_for_active_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(arena_tournament(status="ROUND_2", current_round=2)),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return([SimpleNamespace(user_id=202)]),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        DailyArenaExtendedSession(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.NOT_PARTICIPANT


@pytest.mark.asyncio
async def test_daily_arena_status_returns_round_waiting_without_pending_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(arena_tournament(status="ROUND_2", current_round=2)),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return([SimpleNamespace(user_id=101)]),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentMatchesRepo,
        "list_by_tournament_round",
        async_return([SimpleNamespace(user_a=101, user_b=202, status="COMPLETED")]),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        DailyArenaExtendedSession(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is DailyCupUserStatus.ROUND_WAITING


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tournament_status", "participant_ids", "expected_status", "expect_tournament"),
    [
        (TOURNAMENT_STATUS_COMPLETED, [101], DailyCupUserStatus.COMPLETED, True),
        (TOURNAMENT_STATUS_COMPLETED, [202], DailyCupUserStatus.NOT_PARTICIPANT, True),
        ("PAUSED", [101], DailyCupUserStatus.NO_TOURNAMENT, False),
    ],
    ids=["completed_participant", "completed_outsider", "unknown_status"],
)
async def test_daily_arena_status_completed_and_fallback_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tournament_status: str,
    participant_ids: list[int],
    expected_status: DailyCupUserStatus,
    expect_tournament: bool,
) -> None:
    # GOLDEN: фіксує поточну поведінку, не змінювати без рев'ю
    patch_status_window(monkeypatch)
    tournament = arena_tournament(status=tournament_status, current_round=3)
    monkeypatch.setattr(
        daily_cup_user_status.TournamentsRepo,
        "get_by_type_and_registration_deadline",
        async_return(tournament),
    )
    monkeypatch.setattr(
        daily_cup_user_status.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return([SimpleNamespace(user_id=user_id) for user_id in participant_ids]),
    )

    snapshot = await daily_cup_user_status.get_daily_cup_status_for_user(
        DailyArenaExtendedSession(),
        user_id=101,
        now_utc=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
    )

    assert snapshot.status is expected_status
    assert (snapshot.tournament is not None) is expect_tournament
