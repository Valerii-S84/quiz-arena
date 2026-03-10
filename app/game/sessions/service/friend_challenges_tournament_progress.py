from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.game.friend_challenges.constants import (
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_WALKOVER,
)
from app.game.sessions.service.friend_challenges_tournament_self_bot import (
    is_self_bot_tournament_challenge,
    maybe_complete_self_bot_match,
)
from app.game.tournaments.constants import (
    DAILY_CUP_MAX_ROUNDS,
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_SELF_BOT_DEFAULT_CORRECT_ANSWERS,
    TOURNAMENT_TYPE_DAILY_ARENA,
    TOURNAMENT_TYPE_DAILY_ELIMINATION,
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


def _ensure_elimination_winner(
    *,
    challenge: FriendChallenge,
    match: TournamentMatch,
) -> tuple[int, int | None]:
    user_a = int(match.user_a)
    user_b = int(match.user_b) if match.user_b is not None else None
    if user_b is None:
        challenge.winner_user_id = user_a
        return user_a, None
    score_a = _score_for_user(challenge=challenge, user_id=user_a)
    score_b = _score_for_user(challenge=challenge, user_id=user_b)
    if score_a > score_b:
        challenge.winner_user_id = user_a
        return user_a, user_b
    if score_b > score_a:
        challenge.winner_user_id = user_b
        return user_b, user_a
    finished_a = _finished_at_for_user(challenge=challenge, user_id=user_a)
    finished_b = _finished_at_for_user(challenge=challenge, user_id=user_b)
    if finished_a is not None and finished_b is not None and finished_a != finished_b:
        winner_id = user_a if finished_a < finished_b else user_b
        loser_id = user_b if winner_id == user_a else user_a
        challenge.winner_user_id = winner_id
        return winner_id, loser_id
    winner_id = random.choice((user_a, user_b))
    loser_id = user_b if winner_id == user_a else user_a
    challenge.winner_user_id = winner_id
    return winner_id, loser_id


async def _update_elimination_timeout_state(
    *,
    challenge: FriendChallenge,
    match: TournamentMatch,
) -> None:
    from app.workers.tasks.daily_elimination_async import (
        enqueue_elimination_match_timeout,
        revoke_elimination_match_timeout,
    )

    if challenge.creator_finished_at is not None and match.player_a_finished_at is None:
        match.player_a_finished_at = challenge.creator_finished_at
    if challenge.opponent_finished_at is not None and match.player_b_finished_at is None:
        match.player_b_finished_at = challenge.opponent_finished_at

    if challenge.status in {DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE}:
        if match.match_timeout_task_id is None:
            match.match_timeout_task_id = enqueue_elimination_match_timeout(match_id=match.id)
        return
    if match.match_timeout_task_id is not None:
        revoke_elimination_match_timeout(task_id=match.match_timeout_task_id)
        match.match_timeout_task_id = None


async def handle_tournament_duel_progress(
    session: AsyncSession,
    *,
    challenge: FriendChallenge,
    user_id: int,
    now_utc: datetime,
) -> None:
    if challenge.tournament_match_id is None:
        return
    from app.game.tournaments.lifecycle import (
        check_and_advance_round,
        on_elimination_match_complete,
    )
    from app.game.tournaments.settlement import settle_pending_match_from_duel
    from app.workers.tasks.daily_cup_match_results import send_daily_cup_match_result_messages

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
    if tournament.type == TOURNAMENT_TYPE_DAILY_ELIMINATION:
        maybe_complete_self_bot_match(challenge=challenge, now_utc=now_utc)
        await _update_elimination_timeout_state(challenge=challenge, match=tournament_match)
        if challenge.status in {DUEL_STATUS_COMPLETED, DUEL_STATUS_WALKOVER}:
            winner_id, loser_id = _ensure_elimination_winner(
                challenge=challenge,
                match=tournament_match,
            )
            match_settled = await settle_pending_match_from_duel(
                session,
                match=tournament_match,
                now_utc=now_utc,
            )
            if match_settled:
                await on_elimination_match_complete(
                    session,
                    match_id=tournament_match.id,
                    winner_id=winner_id,
                    loser_id=loser_id,
                    now_utc=now_utc,
                )
        return
    if tournament.type != TOURNAMENT_TYPE_DAILY_ARENA:
        return
    if is_self_bot_tournament_challenge(challenge=challenge):
        maybe_complete_self_bot_match(
            challenge=challenge,
            now_utc=now_utc,
            fixed_bot_score=TOURNAMENT_SELF_BOT_DEFAULT_CORRECT_ANSWERS,
        )
    if challenge.status in {DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE}:
        if tournament_match.status == TOURNAMENT_MATCH_STATUS_PENDING:
            response_deadline = now_utc + timedelta(minutes=_DAILY_CUP_TURN_RESPONSE_GRACE_MINUTES)
            tightened_deadline = min(tournament_match.deadline, response_deadline)
            if tightened_deadline < tournament_match.deadline:
                tournament_match.deadline = tightened_deadline
            if tournament.round_deadline is None or tightened_deadline < tournament.round_deadline:
                tournament.round_deadline = tightened_deadline
    if challenge.status not in {DUEL_STATUS_COMPLETED, DUEL_STATUS_WALKOVER}:
        return

    match_settled = await settle_pending_match_from_duel(
        session,
        match=tournament_match,
        now_utc=now_utc,
    )
    if not match_settled:
        return
    transition = await check_and_advance_round(
        session,
        tournament_id=tournament_match.tournament_id,
        now_utc=now_utc,
    )

    await emit_analytics_event(
        session,
        event_type="daily_cup_match_completed",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={
            "tournament_id": str(tournament_match.tournament_id),
            "round_no": int(tournament_match.round_no),
        },
    )
    if int(transition["round_started"]) > 0:
        await emit_analytics_event(
            session,
            event_type="daily_cup_round_started",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={
                "tournament_id": str(tournament_match.tournament_id),
                "round_no": int(tournament.current_round),
            },
        )
    if int(transition["tournament_completed"]) > 0:
        from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging

        enqueue_daily_cup_round_messaging(
            tournament_id=str(tournament_match.tournament_id),
            enqueue_completion_followups=True,
        )
    if challenge.opponent_user_id is not None and tournament_match.user_b is not None:
        await send_daily_cup_match_result_messages(
            session,
            tournament_id=tournament_match.tournament_id,
            round_no=int(tournament_match.round_no),
            user_a=int(tournament_match.user_a),
            user_b=int(tournament_match.user_b),
            user_a_points=int(challenge.creator_score),
            user_b_points=int(challenge.opponent_score),
            rounds_total=DAILY_CUP_MAX_ROUNDS,
            tournament_registration_deadline=tournament.registration_deadline,
            next_round_start_time=(
                tournament.round_start_time
                if int(tournament.current_round) == int(tournament_match.round_no) + 1
                else None
            ),
        )
