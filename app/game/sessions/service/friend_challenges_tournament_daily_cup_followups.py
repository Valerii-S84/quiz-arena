from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.game.tournaments.constants import daily_cup_max_rounds_for_participants


def enqueue_daily_cup_completion_followups(
    *,
    tournament_id: str,
    transition: dict[str, int],
) -> None:
    if int(transition["tournament_completed"]) <= 0:
        return
    from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging

    enqueue_daily_cup_round_messaging(
        tournament_id=tournament_id,
        enqueue_completion_followups=True,
    )


def _next_daily_cup_round_start_time(
    *,
    tournament: Tournament,
    tournament_match: TournamentMatch,
) -> datetime | None:
    if int(tournament.current_round) != int(tournament_match.round_no) + 1:
        return None
    return tournament.round_start_time


async def send_daily_cup_match_results_if_ready(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    tournament_match: TournamentMatch,
    tournament: Tournament,
) -> None:
    if challenge.opponent_user_id is None or tournament_match.user_b is None:
        return
    from app.workers.tasks.daily_cup_match_results import send_daily_cup_match_result_messages

    participants_total = await TournamentParticipantsRepo.count_for_tournament(
        session,
        tournament_id=tournament_match.tournament_id,
    )
    await send_daily_cup_match_result_messages(
        session,
        tournament_id=tournament_match.tournament_id,
        round_no=int(tournament_match.round_no),
        user_a=int(tournament_match.user_a),
        user_b=int(tournament_match.user_b),
        user_a_points=int(challenge.creator_score),
        user_b_points=int(challenge.opponent_score),
        rounds_total=daily_cup_max_rounds_for_participants(participants_total=participants_total),
        tournament_registration_deadline=tournament.registration_deadline,
        next_round_start_time=_next_daily_cup_round_start_time(
            tournament=tournament,
            tournament_match=tournament_match,
        ),
    )
