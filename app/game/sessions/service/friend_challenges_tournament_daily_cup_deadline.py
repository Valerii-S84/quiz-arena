from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.game.tournaments.constants import TOURNAMENT_MATCH_STATUS_PENDING

_DAILY_CUP_CHALLENGE_AWAITING_RESPONSE = frozenset({"CREATOR_DONE", "OPPONENT_DONE"})
_DAILY_CUP_CHALLENGE_FINISHED = frozenset({"COMPLETED", "WALKOVER"})


def tighten_daily_cup_deadline(
    *,
    challenge: FriendChallenge,
    tournament_match: TournamentMatch,
    tournament: Tournament,
    now_utc: datetime,
    grace_minutes: int,
) -> None:
    if challenge.status not in _DAILY_CUP_CHALLENGE_AWAITING_RESPONSE:
        return
    if tournament_match.status != TOURNAMENT_MATCH_STATUS_PENDING:
        return
    response_deadline = now_utc + timedelta(minutes=grace_minutes)
    tightened_deadline = min(tournament_match.deadline, response_deadline)
    if tightened_deadline < tournament_match.deadline:
        tournament_match.deadline = tightened_deadline
    if tournament.round_deadline is None or tightened_deadline < tournament.round_deadline:
        tournament.round_deadline = tightened_deadline


def should_continue_daily_cup_progress(
    *,
    challenge: FriendChallenge,
    tournament_match: TournamentMatch,
    tournament: Tournament,
    now_utc: datetime,
    grace_minutes: int,
) -> bool:
    tighten_daily_cup_deadline(
        challenge=challenge,
        tournament_match=tournament_match,
        tournament=tournament,
        now_utc=now_utc,
        grace_minutes=grace_minutes,
    )
    return challenge.status in _DAILY_CUP_CHALLENGE_FINISHED
