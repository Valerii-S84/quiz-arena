from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.db.models.tournament_matches import TournamentMatch
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_COMPLETED,
    TOURNAMENT_MATCH_STATUS_WALKOVER,
)
from app.game.tournaments.settlement import (
    _match_scores_from_challenge,
    _score_deltas_for_match,
    _valid_winner_for_match,
)


def _build_match(*, user_a: int, user_b: int | None) -> TournamentMatch:
    return TournamentMatch(
        id=uuid4(),
        tournament_id=uuid4(),
        round_no=1,
        user_a=user_a,
        user_b=user_b,
        friend_challenge_id=None,
        status="PENDING",
        winner_id=None,
        deadline=datetime.now(UTC),
    )


def test_score_deltas_for_completed_draw_gives_half_point_each() -> None:
    deltas = _score_deltas_for_match(
        match_status=TOURNAMENT_MATCH_STATUS_COMPLETED,
        winner_id=None,
        user_a=11,
        user_b=22,
        score_a=4,
        score_b=4,
    )
    assert deltas == [
        (11, Decimal("0.5"), Decimal("4")),
        (22, Decimal("0.5"), Decimal("4")),
    ]


def test_score_deltas_for_walkover_without_winner_gives_zero_points() -> None:
    deltas = _score_deltas_for_match(
        match_status=TOURNAMENT_MATCH_STATUS_WALKOVER,
        winner_id=None,
        user_a=11,
        user_b=22,
        score_a=3,
        score_b=2,
    )
    assert deltas == [
        (11, Decimal("0"), Decimal("3")),
        (22, Decimal("0"), Decimal("2")),
    ]


def test_valid_winner_for_match_rejects_user_outside_pair() -> None:
    match = _build_match(user_a=11, user_b=22)
    assert _valid_winner_for_match(match=match, winner_id=33) is None
    assert _valid_winner_for_match(match=match, winner_id=11) == 11
    assert _valid_winner_for_match(match=match, winner_id=22) == 22


def test_match_scores_from_challenge_swaps_when_creator_is_user_b() -> None:
    match = _build_match(user_a=11, user_b=22)
    score_a, score_b = _match_scores_from_challenge(
        match=match,
        challenge_creator_user_id=22,
        challenge_creator_score=5,
        challenge_opponent_score=2,
    )
    assert score_a == 2
    assert score_b == 5
