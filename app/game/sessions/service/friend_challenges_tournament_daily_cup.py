from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
)
from app.game.sessions.service.friend_challenges_tournament_daily_cup_followups import (
    enqueue_daily_cup_completion_followups,
    send_daily_cup_match_results_if_ready,
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
    enqueue_daily_cup_completion_followups(
        tournament_id=tournament_id,
        transition=transition,
    )
    await send_daily_cup_match_results_if_ready(
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
