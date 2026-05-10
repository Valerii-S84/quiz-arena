from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.tournaments import queries
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_COMPLETED,
    TOURNAMENT_STATUS_ROUND_1,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.errors import TournamentAccessError, TournamentNotFoundError
from tests.game.tournaments_unit_support import (
    NOW_UTC,
    TournamentSession,
    async_return,
    match_row,
    participant_row,
    tournament_row,
)


def test_resolve_viewer_current_match_covers_pair_and_bye_states() -> None:
    challenge_id = uuid4()

    assert queries._resolve_viewer_current_match(
        matches=[match_row(user_a=11, user_b=None, challenge_id=challenge_id)],
        viewer_user_id=11,
    ) == (challenge_id, None)
    assert queries._resolve_viewer_current_match(
        matches=[match_row(user_a=11, user_b=22, challenge_id=challenge_id)],
        viewer_user_id=22,
    ) == (challenge_id, 11)
    assert queries._resolve_viewer_current_match(
        matches=[match_row(user_a=11, user_b=22, status=TOURNAMENT_MATCH_STATUS_COMPLETED)],
        viewer_user_id=11,
    ) == (None, 22)
    assert queries._resolve_viewer_current_match(
        matches=[match_row(user_a=11, user_b=None)],
        viewer_user_id=11,
    ) == (None, None)


@pytest.mark.asyncio
async def test_build_lobby_snapshot_private_round_includes_current_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tournament = tournament_row(status=TOURNAMENT_STATUS_ROUND_1, current_round=1)
    challenge_id = uuid4()
    monkeypatch.setattr(
        queries.TournamentParticipantsRepo,
        "list_for_tournament",
        async_return(
            [
                participant_row(tournament_id=tournament.id, user_id=11),
                participant_row(tournament_id=tournament.id, user_id=22),
            ]
        ),
    )
    monkeypatch.setattr(
        queries.TournamentMatchesRepo,
        "list_by_tournament_round",
        async_return([match_row(tournament_id=tournament.id, challenge_id=challenge_id)]),
    )

    snapshot = await queries._build_lobby_snapshot(
        session=TournamentSession(),
        tournament=tournament,
        viewer_user_id=11,
        now_utc=NOW_UTC,
    )

    assert snapshot.viewer_joined
    assert snapshot.viewer_is_creator
    assert not snapshot.can_join
    assert snapshot.viewer_current_match_challenge_id == challenge_id
    assert snapshot.viewer_current_opponent_user_id == 22


@pytest.mark.asyncio
async def test_build_lobby_snapshot_daily_uses_standings(monkeypatch: pytest.MonkeyPatch) -> None:
    tournament = tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA, created_by=None)
    participant = participant_row(tournament_id=tournament.id, user_id=44)
    monkeypatch.setattr(
        queries,
        "calculate_daily_cup_standings",
        async_return([SimpleNamespace(participant=participant)]),
    )

    snapshot = await queries._build_lobby_snapshot(
        session=TournamentSession(),
        tournament=tournament,
        viewer_user_id=55,
        now_utc=NOW_UTC,
    )

    assert snapshot.participants[0].user_id == 44
    assert snapshot.can_join
    assert not snapshot.can_start


@pytest.mark.asyncio
async def test_lobby_entrypoints_raise_not_found_and_access_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(queries.TournamentsRepo, "get_by_id", async_return(None))
    with pytest.raises(TournamentNotFoundError):
        await queries.get_private_tournament_lobby_by_id(
            TournamentSession(),
            tournament_id=uuid4(),
            viewer_user_id=11,
        )

    monkeypatch.setattr(queries.TournamentsRepo, "get_by_invite_code", async_return(None))
    with pytest.raises(TournamentNotFoundError):
        await queries.get_private_tournament_lobby_by_invite_code(
            TournamentSession(),
            invite_code="missing",
            viewer_user_id=11,
        )

    monkeypatch.setattr(
        queries.TournamentsRepo,
        "get_by_id",
        async_return(tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA)),
    )
    with pytest.raises(TournamentAccessError):
        await queries.get_private_tournament_lobby_by_id(
            TournamentSession(),
            tournament_id=uuid4(),
            viewer_user_id=11,
        )

    monkeypatch.setattr(queries.TournamentsRepo, "get_by_id", async_return(tournament_row()))
    with pytest.raises(TournamentAccessError):
        await queries.get_daily_cup_lobby_by_id(
            TournamentSession(),
            tournament_id=uuid4(),
            viewer_user_id=11,
        )
