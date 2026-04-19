from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.game.sessions.service.friend_challenges_tournament_daily_cup_deadline import (
    should_continue_daily_cup_progress,
)
from app.game.sessions.service.friend_challenges_tournament_daily_cup_followups import (
    enqueue_daily_cup_completion_followups,
    send_daily_cup_match_results_if_ready,
)


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
    if not should_continue_daily_cup_progress(
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
