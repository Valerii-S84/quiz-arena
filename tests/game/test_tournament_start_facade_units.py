from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.tournaments import start
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED, TOURNAMENT_TYPE_DAILY_ARENA
from app.game.tournaments.errors import (
    TournamentAccessError,
    TournamentAlreadyStartedError,
    TournamentClosedError,
    TournamentInsufficientParticipantsError,
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
async def test_start_private_tournament_success(monkeypatch: pytest.MonkeyPatch) -> None:
    tournament = tournament_row(created_by=11)
    monkeypatch.setattr(start.TournamentsRepo, "get_by_id_for_update", async_return(tournament))
    monkeypatch.setattr(
        start.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        async_return(
            [
                participant_row(tournament_id=tournament.id, user_id=11),
                participant_row(tournament_id=tournament.id, user_id=22),
            ]
        ),
    )
    monkeypatch.setattr(start, "create_round_matches", async_return(1))

    result = await start.start_private_tournament(
        TournamentSession(),
        creator_user_id=11,
        tournament_id=tournament.id,
        now_utc=NOW_UTC,
    )

    assert result.round_no == 1
    assert result.matches_total == 1
    assert tournament.status == "ROUND_1"
    assert tournament.current_round == 1
    assert tournament.round_deadline is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tournament", "creator_user_id", "error_type"),
    [
        (None, 11, TournamentNotFoundError),
        (tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA), 11, TournamentAccessError),
        (tournament_row(created_by=22), 11, TournamentAccessError),
        (tournament_row(status=TOURNAMENT_STATUS_COMPLETED), 11, TournamentAlreadyStartedError),
        (tournament_row(registration_deadline=NOW_UTC), 11, TournamentClosedError),
    ],
)
async def test_start_private_tournament_error_branches(
    monkeypatch: pytest.MonkeyPatch,
    tournament,
    creator_user_id: int,
    error_type: type[Exception],
) -> None:
    monkeypatch.setattr(start.TournamentsRepo, "get_by_id_for_update", async_return(tournament))

    with pytest.raises(error_type):
        await start.start_private_tournament(
            TournamentSession(),
            creator_user_id=creator_user_id,
            tournament_id=uuid4(),
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_start_private_tournament_rejects_too_few_participants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(created_by=11)
    monkeypatch.setattr(start.TournamentsRepo, "get_by_id_for_update", async_return(tournament))
    monkeypatch.setattr(
        start.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        async_return([participant_row(tournament_id=tournament.id, user_id=11)]),
    )

    with pytest.raises(TournamentInsufficientParticipantsError):
        await start.start_private_tournament(
            TournamentSession(),
            creator_user_id=11,
            tournament_id=tournament.id,
            now_utc=NOW_UTC,
        )
