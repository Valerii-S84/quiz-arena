from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    daily_cup_max_rounds_for_participants,
)

_DAILY_CUP_CHALLENGE_AWAITING_RESPONSE = frozenset({"CREATOR_DONE", "OPPONENT_DONE"})
_DAILY_CUP_CHALLENGE_FINISHED = frozenset({"COMPLETED", "WALKOVER"})


def _tighten_daily_cup_deadline(
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


def _should_continue_daily_cup_progress(
    *,
    challenge: FriendChallenge,
    tournament_match: TournamentMatch,
    tournament: Tournament,
    now_utc: datetime,
    grace_minutes: int,
) -> bool:
    _tighten_daily_cup_deadline(
        challenge=challenge,
        tournament_match=tournament_match,
        tournament=tournament,
        now_utc=now_utc,
        grace_minutes=grace_minutes,
    )
    return challenge.status in _DAILY_CUP_CHALLENGE_FINISHED


async def _settle_daily_cup_match_and_advance_round(
    session: AsyncSession,
    *,
    tournament_match: TournamentMatch,
    now_utc: datetime,
) -> dict[str, int] | None:
    from app.game.tournaments.lifecycle import check_and_advance_round
    from app.game.tournaments.settlement import settle_pending_match_from_duel

    match_settled = await settle_pending_match_from_duel(
        session,
        match=tournament_match,
        now_utc=now_utc,
    )
    if not match_settled:
        return None
    return await check_and_advance_round(
        session,
        tournament_id=tournament_match.tournament_id,
        now_utc=now_utc,
    )


async def _emit_daily_cup_progress_events(
    session: AsyncSession,
    *,
    tournament_match: TournamentMatch,
    tournament: Tournament,
    transition: dict[str, int],
    user_id: int,
    now_utc: datetime,
) -> None:
    tournament_id = str(tournament_match.tournament_id)
    await emit_analytics_event(
        session,
        event_type="daily_cup_match_completed",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "tournament_id": tournament_id,
            "round_no": int(tournament_match.round_no),
        },
    )
    if int(transition["round_started"]) <= 0:
        return
    await emit_analytics_event(
        session,
        event_type="daily_cup_round_started",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "tournament_id": tournament_id,
            "round_no": int(tournament.current_round),
        },
    )


def _maybe_enqueue_daily_cup_completion_followups(
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


async def _send_daily_cup_match_results_if_ready(
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


async def _process_finished_daily_cup_progress(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
    tournament_match: TournamentMatch,
    tournament: Tournament,
) -> None:
    transition = await _settle_daily_cup_match_and_advance_round(
        session,
        tournament_match=tournament_match,
        now_utc=now_utc,
    )
    if transition is None:
        return
    tournament_id = str(tournament_match.tournament_id)
    await _emit_daily_cup_progress_events(
        session,
        tournament_match=tournament_match,
        tournament=tournament,
        transition=transition,
        user_id=user_id,
        now_utc=now_utc,
    )
    _maybe_enqueue_daily_cup_completion_followups(
        tournament_id=tournament_id,
        transition=transition,
    )
    await _send_daily_cup_match_results_if_ready(
        session,
        challenge=challenge,
        tournament_match=tournament_match,
        tournament=tournament,
    )


async def handle_daily_cup_tournament_progress(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
    tournament_match: TournamentMatch,
    tournament: Tournament,
    grace_minutes: int,
) -> None:
    if not _should_continue_daily_cup_progress(
        challenge=challenge,
        tournament_match=tournament_match,
        tournament=tournament,
        now_utc=now_utc,
        grace_minutes=grace_minutes,
    ):
        return

    await _process_finished_daily_cup_progress(
        session,
        challenge=challenge,
        user_id=user_id,
        now_utc=now_utc,
        tournament_match=tournament_match,
        tournament=tournament,
    )
