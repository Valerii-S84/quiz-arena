from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.sessions.service.friend_challenges_tournament_daily_cup import (
    handle_daily_cup_tournament_progress,
)
from app.game.sessions.service.friend_challenges_tournament_self_bot import (
    is_self_bot_tournament_challenge,
    maybe_complete_self_bot_match,
)
from app.game.tournaments.constants import (
    TOURNAMENT_SELF_BOT_DEFAULT_CORRECT_ANSWERS,
    TOURNAMENT_TYPE_DAILY_ARENA,
)

_DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES = max(
    1,
    int(os.getenv("DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES", "15")),
)


def _score_for_user(*, challenge: FriendChallenge, user_id: int) -> int:
    if int(challenge.creator_user_id) == int(user_id):
        return int(challenge.creator_score)
    return int(challenge.opponent_score)


def _finished_at_for_user(*, challenge: FriendChallenge, user_id: int) -> datetime | None:
    if int(challenge.creator_user_id) == int(user_id):
        return challenge.creator_finished_at
    return challenge.opponent_finished_at


async def handle_tournament_duel_progress(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
) -> None:
    if challenge.tournament_match_id is None:
        return

    tournament_match = await TournamentMatchesRepo.get_by_id_for_update(
        session,
        challenge.tournament_match_id,
    )
    if tournament_match is None:
        return
    tournament = await TournamentsRepo.get_by_id(
        session,
        tournament_match.tournament_id,
    )
    if tournament is None:
        return
    if tournament.type != TOURNAMENT_TYPE_DAILY_ARENA:
        return
    if is_self_bot_tournament_challenge(challenge=challenge):
        maybe_complete_self_bot_match(
            challenge=challenge,
            now_utc=now_utc,
            fixed_bot_score=TOURNAMENT_SELF_BOT_DEFAULT_CORRECT_ANSWERS,
        )
    await handle_daily_cup_tournament_progress(
        session,
        challenge=challenge,
        user_id=user_id,
        now_utc=now_utc,
        tournament_match=tournament_match,
        tournament=tournament,
        grace_minutes=_DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES,
    )
