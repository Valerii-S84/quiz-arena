from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.workers.tasks import daily_cup_rounds_processing as processing
from tests.game.tournaments_unit_support import NOW_UTC


def test_match_scores_from_challenge_swaps_creator_side() -> None:
    challenge = SimpleNamespace(creator_user_id=22, creator_score=7, opponent_score=3)
    match = SimpleNamespace(user_a=11)

    assert processing.match_scores_from_challenge(match=match, challenge=challenge) == (3, 7)


@pytest.mark.asyncio
async def test_advance_due_daily_cup_rounds_collects_events_and_walkovers() -> None:
    tournament_id = uuid4()
    challenge_id = uuid4()
    tournament = SimpleNamespace(
        id=tournament_id,
        status="ROUND_1",
        current_round=1,
        registration_deadline=NOW_UTC,
        round_start_time=NOW_UTC,
    )
    pending_match = SimpleNamespace(id=uuid4(), status="PENDING")
    settled_match = SimpleNamespace(
        id=pending_match.id,
        tournament_id=tournament_id,
        round_no=1,
        user_a=11,
        user_b=22,
        status="WALKOVER",
        winner_id=11,
        friend_challenge_id=challenge_id,
    )
    matches_repo = _MatchesRepo([pending_match], [settled_match])
    challenge = SimpleNamespace(creator_user_id=11, creator_score=5, opponent_score=2)

    async def _settle_round_and_advance(*_args, **_kwargs):
        tournament.current_round = 2
        return {
            "matches_settled": 1,
            "round_started": 1,
            "tournament_completed": 0,
            "matches_created": 2,
        }

    outcome = await processing.advance_due_daily_cup_rounds(
        session=object(),
        now_utc_value=NOW_UTC,
        tournaments_repo=SimpleNamespace(
            list_due_round_deadline_for_update=_async_return([tournament])
        ),
        participants_repo=SimpleNamespace(count_for_tournament=_async_return(16)),
        matches_repo=matches_repo,
        challenges_repo=SimpleNamespace(get_by_id=_async_return(challenge)),
        settle_round_and_advance_fn=_settle_round_and_advance,
        tournament_type_daily_arena="DAILY_ARENA",
        pending_match_status="PENDING",
        walkover_match_status="WALKOVER",
        tournament_completed_status="COMPLETED",
        max_rounds_fn=lambda *, participants_total: 3,
    )

    assert outcome.rounds_started_total == 1
    assert outcome.matches_created_total == 2
    assert {event["event_type"] for event in outcome.events} == {
        "daily_cup_match_completed",
        "daily_cup_round_started",
    }
    assert outcome.walkover_notifications[0].user_a_points == 5
    assert outcome.walkover_notifications[0].next_round_start_time is tournament.round_start_time


@pytest.mark.asyncio
async def test_advance_due_daily_cup_rounds_skips_walkover_without_challenge() -> None:
    tournament = SimpleNamespace(id=uuid4(), status="ROUND_4", current_round=4)
    match = SimpleNamespace(id=uuid4(), status="PENDING")
    matches_repo = _MatchesRepo(
        [match],
        [
            SimpleNamespace(
                id=match.id,
                status="WALKOVER",
                user_b=22,
                winner_id=11,
                friend_challenge_id=uuid4(),
            )
        ],
    )

    outcome = await processing.advance_due_daily_cup_rounds(
        session=object(),
        now_utc_value=NOW_UTC,
        tournaments_repo=SimpleNamespace(
            list_due_round_deadline_for_update=_async_return([tournament])
        ),
        participants_repo=SimpleNamespace(count_for_tournament=_async_return(16)),
        matches_repo=matches_repo,
        challenges_repo=SimpleNamespace(get_by_id=_async_return(None)),
        settle_round_and_advance_fn=_async_return(
            {
                "matches_settled": 1,
                "round_started": 0,
                "tournament_completed": 1,
                "matches_created": 0,
            }
        ),
        tournament_type_daily_arena="DAILY_ARENA",
        pending_match_status="PENDING",
        walkover_match_status="WALKOVER",
        tournament_completed_status="COMPLETED",
        max_rounds_fn=lambda *, participants_total: 3,
    )

    assert outcome.completed_ids == [str(tournament.id)]
    assert outcome.walkover_notifications == []


class _MatchesRepo:
    def __init__(self, first_round_matches: list[Any], second_round_matches: list[Any]):
        self._calls = 0
        self._round_matches = [first_round_matches, second_round_matches]

    async def list_by_tournament_round_for_update(self, *_args, **_kwargs):
        result = self._round_matches[self._calls]
        self._calls += 1
        return result


def _async_return(value: object):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
