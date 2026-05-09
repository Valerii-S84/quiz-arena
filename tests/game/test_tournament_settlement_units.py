from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.tournaments import settlement
from app.game.tournaments.constants import TOURNAMENT_TYPE_DAILY_ARENA
from tests.game.tournaments_unit_support import (
    NOW_UTC,
    TournamentSession,
    async_return,
    match_row,
    tournament_row,
)


@pytest.mark.asyncio
async def test_settle_pending_match_walkover_without_challenge() -> None:
    match = match_row(challenge_id=None)

    assert await settlement.settle_pending_match_from_duel(
        TournamentSession(),
        match=match,
        now_utc=NOW_UTC,
    )
    assert match.status == "WALKOVER"
    assert match.winner_id is None


@pytest.mark.asyncio
async def test_settle_pending_match_ignores_non_pending_and_missing_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = match_row(status="COMPLETED", challenge_id=uuid4())
    assert not await settlement.settle_pending_match_from_duel(
        TournamentSession(),
        match=completed,
        now_utc=NOW_UTC,
    )

    missing = match_row(challenge_id=uuid4())
    monkeypatch.setattr(
        settlement.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )
    assert await settlement.settle_pending_match_from_duel(
        TournamentSession(),
        match=missing,
        now_utc=NOW_UTC,
    )
    assert missing.status == "WALKOVER"


@pytest.mark.asyncio
async def test_settle_pending_match_completed_applies_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = match_row(challenge_id=uuid4())
    applied: list[dict[str, object]] = []
    challenge = SimpleNamespace(
        status="COMPLETED",
        opponent_user_id=22,
        expires_at=NOW_UTC + timedelta(hours=1),
        creator_user_id=11,
        creator_score=5,
        opponent_score=3,
        winner_user_id=11,
    )

    async def _apply_score_delta(_session, **kwargs) -> None:
        applied.append(kwargs)

    monkeypatch.setattr(
        settlement.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(settlement.TournamentsRepo, "get_by_id", async_return(tournament_row()))
    monkeypatch.setattr(
        settlement.TournamentParticipantsRepo,
        "apply_score_delta",
        _apply_score_delta,
    )

    assert await settlement.settle_pending_match_from_duel(
        TournamentSession(),
        match=match,
        now_utc=NOW_UTC,
    )
    assert match.status == "COMPLETED"
    assert match.winner_id == 11
    assert [item["score_delta"] for item in applied] == [
        settlement.Decimal("1"),
        settlement.Decimal("0"),
    ]


@pytest.mark.asyncio
async def test_settle_pending_match_waits_before_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    match = match_row(challenge_id=uuid4())
    match.deadline = NOW_UTC + timedelta(hours=1)
    challenge = SimpleNamespace(
        status="ACCEPTED",
        opponent_user_id=22,
        expires_at=NOW_UTC + timedelta(hours=2),
        creator_user_id=11,
        creator_score=0,
        opponent_score=0,
        winner_user_id=None,
    )
    monkeypatch.setattr(
        settlement.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )

    assert not await settlement.settle_pending_match_from_duel(
        TournamentSession(),
        match=match,
        now_utc=NOW_UTC,
    )
    assert challenge.expires_at == match.deadline


@pytest.mark.asyncio
async def test_settle_pending_daily_cup_stores_player_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = match_row(challenge_id=uuid4())
    stored: list[object] = []
    challenge = SimpleNamespace(
        status="WALKOVER",
        opponent_user_id=22,
        expires_at=NOW_UTC,
        creator_user_id=22,
        creator_score=2,
        opponent_score=5,
        winner_user_id=22,
    )

    async def _store(_session, **kwargs) -> None:
        stored.append(kwargs["result"])

    monkeypatch.setattr(
        settlement.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(challenge),
    )
    monkeypatch.setattr(
        settlement.TournamentsRepo,
        "get_by_id",
        async_return(tournament_row(type=TOURNAMENT_TYPE_DAILY_ARENA)),
    )
    monkeypatch.setattr(
        settlement,
        "build_daily_cup_player_results",
        async_return(("creator-result", "opponent-result")),
    )
    monkeypatch.setattr(settlement, "store_daily_cup_player_result", _store)

    assert await settlement.settle_pending_match_from_duel(
        TournamentSession(),
        match=match,
        now_utc=NOW_UTC,
    )
    assert match.status == "WALKOVER"
    assert stored == ["creator-result", "opponent-result"]
