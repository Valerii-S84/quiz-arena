from __future__ import annotations

import pytest

from app.db.models.tournaments import Tournament
from app.game.tournaments import create_join
from app.game.tournaments.constants import (
    TOURNAMENT_FORMAT_QUICK_5,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.errors import (
    TournamentAccessError,
    TournamentClosedError,
    TournamentFullError,
    TournamentNotFoundError,
)
from tests.game.tournaments_unit_support import (
    NOW_UTC,
    TournamentSession,
    async_return,
    participant_row,
    tournament_row,
)


@pytest.mark.asyncio
async def test_create_private_tournament_clamps_capacity_and_joins_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_rows: list[Tournament] = []
    joined_rows: list[dict[str, object]] = []

    async def _create(_session, *, tournament: Tournament) -> Tournament:
        created_rows.append(tournament)
        return tournament

    async def _create_once(_session, **kwargs) -> bool:
        joined_rows.append(kwargs)
        return True

    monkeypatch.setattr(create_join, "generate_invite_code", async_return("code-1"))
    monkeypatch.setattr(create_join.TournamentsRepo, "create", _create)
    monkeypatch.setattr(create_join.TournamentParticipantsRepo, "create_once", _create_once)

    snapshot = await create_join.create_private_tournament(
        TournamentSession(),
        created_by=11,
        format_code=TOURNAMENT_FORMAT_QUICK_5,
        now_utc=NOW_UTC,
        max_participants=999,
    )

    assert snapshot.invite_code == "code-1"
    assert created_rows[0].max_participants == create_join.TOURNAMENT_DEFAULT_MAX_PARTICIPANTS
    assert joined_rows[0]["user_id"] == 11


@pytest.mark.asyncio
async def test_create_private_tournament_rejects_unknown_format() -> None:
    with pytest.raises(TournamentAccessError):
        await create_join.create_private_tournament(
            TournamentSession(),
            created_by=11,
            format_code="SLOW",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_join_private_tournament_returns_existing_and_full_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(max_participants=2)
    monkeypatch.setattr(
        create_join.TournamentsRepo,
        "get_by_invite_code_for_update",
        async_return(tournament),
    )
    monkeypatch.setattr(
        create_join.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        async_return(
            [
                participant_row(tournament_id=tournament.id, user_id=11),
                participant_row(tournament_id=tournament.id, user_id=22),
            ]
        ),
    )

    existing = await create_join.join_private_tournament_by_code(
        TournamentSession(),
        user_id=11,
        invite_code="invite-code",
        now_utc=NOW_UTC,
    )
    assert not existing.joined_now
    assert existing.participants_total == 2

    with pytest.raises(TournamentFullError):
        await create_join.join_private_tournament_by_code(
            TournamentSession(),
            user_id=33,
            invite_code="invite-code",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tournament", "error_type"),
    [
        (None, TournamentNotFoundError),
        (tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA), TournamentAccessError),
        (tournament_row(status=TOURNAMENT_STATUS_COMPLETED), TournamentClosedError),
        (tournament_row(registration_deadline=NOW_UTC), TournamentClosedError),
    ],
)
async def test_join_private_tournament_error_branches(
    monkeypatch: pytest.MonkeyPatch,
    tournament: Tournament | None,
    error_type: type[Exception],
) -> None:
    monkeypatch.setattr(
        create_join.TournamentsRepo,
        "get_by_invite_code_for_update",
        async_return(tournament),
    )

    with pytest.raises(error_type):
        await create_join.join_private_tournament_by_code(
            TournamentSession(),
            user_id=33,
            invite_code="invite-code",
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_join_daily_cup_adds_new_participant(monkeypatch: pytest.MonkeyPatch) -> None:
    tournament = tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA)
    monkeypatch.setattr(
        create_join.TournamentsRepo, "get_by_id_for_update", async_return(tournament)
    )
    monkeypatch.setattr(
        create_join.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        async_return([participant_row(tournament_id=tournament.id, user_id=11)]),
    )
    monkeypatch.setattr(create_join.TournamentParticipantsRepo, "create_once", async_return(True))

    result = await create_join.join_daily_cup_by_id(
        TournamentSession(),
        user_id=22,
        tournament_id=tournament.id,
        now_utc=NOW_UTC,
    )

    assert result.joined_now
    assert result.participants_total == 2
