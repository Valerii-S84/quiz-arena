from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.tournament_matches import TournamentMatch
from app.game.tournaments import lifecycle, rounds
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_COMPLETED,
    TOURNAMENT_STATUS_ROUND_1,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from tests.game.tournaments_unit_support import (
    NOW_UTC,
    TournamentSession,
    async_return,
    match_row,
    participant_row,
    tournament_row,
)


@pytest.mark.asyncio
async def test_create_round_matches_private_bye(monkeypatch: pytest.MonkeyPatch) -> None:
    tournament = tournament_row()
    created_matches: list[TournamentMatch] = []
    applied: list[dict[str, object]] = []

    async def _apply_score_delta(_session, **kwargs) -> None:
        applied.append(kwargs)

    async def _create_many(_session, *, matches: list[TournamentMatch]) -> None:
        created_matches.extend(matches)

    monkeypatch.setattr(
        rounds,
        "build_swiss_pairs",
        lambda **_kwargs: [SimpleNamespace(user_a=11, user_b=None)],
    )
    monkeypatch.setattr(rounds.TournamentParticipantsRepo, "apply_score_delta", _apply_score_delta)
    monkeypatch.setattr(rounds.TournamentMatchesRepo, "create_many", _create_many)

    count = await rounds.create_round_matches(
        TournamentSession(),
        tournament=tournament,
        round_no=1,
        participants=[participant_row(tournament_id=tournament.id, user_id=11)],
        previous_pairs=set(),
        bye_history=set(),
        deadline=NOW_UTC,
        now_utc=NOW_UTC,
    )

    assert count == 1
    assert created_matches[0].status == "WALKOVER"
    assert applied[0]["score_delta"] == Decimal("1")


@pytest.mark.asyncio
async def test_create_round_matches_daily_cup_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    tournament = tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA)
    created_matches: list[TournamentMatch] = []

    async def _create_many(_session, *, matches: list[TournamentMatch]) -> None:
        created_matches.extend(matches)

    monkeypatch.setattr(
        rounds,
        "build_swiss_pairs",
        lambda **_kwargs: [SimpleNamespace(user_a=11, user_b=22)],
    )
    monkeypatch.setattr(rounds.TournamentMatchesRepo, "create_many", _create_many)
    monkeypatch.setattr(
        rounds.GameSessionService,
        "create_tournament_match_friend_challenge",
        async_return(SimpleNamespace(challenge_id=uuid4())),
    )

    count = await rounds.create_round_matches(
        TournamentSession(),
        tournament=tournament,
        round_no=1,
        participants=[
            participant_row(tournament_id=tournament.id, user_id=11),
            participant_row(tournament_id=tournament.id, user_id=22),
        ],
        previous_pairs=set(),
        bye_history=set(),
        deadline=NOW_UTC,
        now_utc=NOW_UTC,
    )

    assert count == 1
    assert created_matches[0].status == "PENDING"
    assert created_matches[0].user_b == 22


@pytest.mark.asyncio
async def test_lifecycle_completes_last_round(monkeypatch: pytest.MonkeyPatch) -> None:
    tournament = tournament_row(status=TOURNAMENT_STATUS_ROUND_1, current_round=4)
    monkeypatch.setattr(
        lifecycle.TournamentMatchesRepo,
        "list_by_tournament_round_for_update",
        async_return([match_row(status=TOURNAMENT_MATCH_STATUS_COMPLETED)]),
    )
    monkeypatch.setattr(
        lifecycle.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        async_return([participant_row(tournament_id=tournament.id, user_id=11)]),
    )
    monkeypatch.setattr(lifecycle, "lock_standings_phase_transition", async_return(None))

    result = await lifecycle.settle_round_and_advance(
        TournamentSession(),
        tournament=tournament,
        now_utc=NOW_UTC,
    )

    assert result["tournament_completed"] == 1
    assert tournament.status == "COMPLETED"


@pytest.mark.asyncio
async def test_lifecycle_advances_to_next_round(monkeypatch: pytest.MonkeyPatch) -> None:
    tournament = tournament_row(status=TOURNAMENT_STATUS_ROUND_1, current_round=1)
    monkeypatch.setattr(
        lifecycle.TournamentMatchesRepo,
        "list_by_tournament_round_for_update",
        async_return([match_row(status=TOURNAMENT_MATCH_STATUS_COMPLETED)]),
    )
    monkeypatch.setattr(
        lifecycle.TournamentParticipantsRepo,
        "list_for_tournament_for_update",
        async_return([participant_row(tournament_id=tournament.id, user_id=11)]),
    )
    monkeypatch.setattr(
        lifecycle.TournamentMatchesRepo, "list_by_tournament_for_update", async_return([])
    )
    monkeypatch.setattr(lifecycle, "create_round_matches", async_return(2))
    monkeypatch.setattr(lifecycle, "lock_standings_phase_transition", async_return(None))

    result = await lifecycle.settle_round_and_advance(
        TournamentSession(),
        tournament=tournament,
        now_utc=NOW_UTC,
    )

    assert result["round_started"] == 1
    assert result["matches_created"] == 2
    assert tournament.current_round == 2
