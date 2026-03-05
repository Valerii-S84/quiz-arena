from __future__ import annotations

import random
from datetime import datetime
from uuid import UUID

import structlog

from app.db.models.friend_challenges import FriendChallenge
from app.db.models.tournament_matches import TournamentMatch
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.friend_challenges.constants import DUEL_STATUS_WALKOVER
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_TYPE_DAILY_ELIMINATION,
)
from app.game.tournaments.lifecycle import on_elimination_match_complete
from app.game.tournaments.settlement import settle_pending_match_from_duel
from app.workers.celery_app import celery_app
from app.workers.tasks.daily_cup_config import DAILY_ELIMINATION_MATCH_TIMEOUT_MINUTES
from app.workers.tasks.daily_cup_core import now_utc

logger = structlog.get_logger("app.workers.tasks.daily_elimination")


def enqueue_elimination_match_timeout(*, match_id: UUID) -> str:
    result = celery_app.send_task(
        "app.workers.tasks.daily_cup.match_timeout",
        kwargs={"match_id": str(match_id)},
        countdown=max(60, int(DAILY_ELIMINATION_MATCH_TIMEOUT_MINUTES) * 60),
        queue="q_normal",
    )
    return str(result.id)


def revoke_elimination_match_timeout(*, task_id: str | None) -> None:
    if not task_id:
        return
    try:
        celery_app.control.revoke(task_id)
    except Exception:
        logger.warning("elimination_match_timeout_revoke_failed", task_id=task_id)


def _resolve_user_scores(
    *,
    challenge: FriendChallenge,
    match: TournamentMatch,
) -> tuple[int, int]:
    creator_user_id = int(challenge.creator_user_id)
    creator_score = int(challenge.creator_score)
    opponent_score = int(challenge.opponent_score)
    if int(match.user_a) == creator_user_id:
        score_a = creator_score
    else:
        score_a = opponent_score
    if match.user_b is None:
        return score_a, 0
    if int(match.user_b) == creator_user_id:
        score_b = creator_score
    else:
        score_b = opponent_score
    return score_a, score_b


def _resolve_winner_loser_for_timeout(
    *,
    challenge: FriendChallenge,
    match: TournamentMatch,
) -> tuple[int, int | None]:
    user_a = int(match.user_a)
    user_b = int(match.user_b) if match.user_b is not None else None
    if user_b is None:
        return user_a, None
    creator_finished = challenge.creator_finished_at is not None
    opponent_finished = challenge.opponent_finished_at is not None
    creator_user = int(challenge.creator_user_id)
    opponent_user = int(challenge.opponent_user_id or challenge.creator_user_id)
    if creator_finished and not opponent_finished:
        winner_id = creator_user
        loser_id = opponent_user
        return winner_id, loser_id
    if opponent_finished and not creator_finished:
        winner_id = opponent_user
        loser_id = creator_user
        return winner_id, loser_id
    score_a, score_b = _resolve_user_scores(challenge=challenge, match=match)
    if score_a > score_b:
        return user_a, user_b
    if score_b > score_a:
        return user_b, user_a
    if match.bracket_slot_a is not None and match.bracket_slot_b is not None:
        if int(match.bracket_slot_a) <= int(match.bracket_slot_b):
            return user_a, user_b
        return user_b, user_a
    winner_id = random.choice((user_a, user_b))
    loser_id = user_b if winner_id == user_a else user_a
    return winner_id, loser_id


def _mark_challenge_forfeit(
    *,
    challenge: FriendChallenge,
    winner_id: int,
    now_utc_value: datetime,
) -> None:
    challenge.status = DUEL_STATUS_WALKOVER
    challenge.winner_user_id = int(winner_id)
    challenge.completed_at = now_utc_value
    challenge.updated_at = now_utc_value
    challenge.expires_at = min(challenge.expires_at, now_utc_value)


async def _settle_single_pending_match(
    *,
    match: TournamentMatch,
    now_utc_value: datetime,
) -> tuple[int, int | None, int]:
    async with SessionLocal.begin() as session:
        locked_match = await TournamentMatchesRepo.get_by_id_for_update(session, match.id)
        if locked_match is None or locked_match.status != TOURNAMENT_MATCH_STATUS_PENDING:
            return 0, None, 0
        tournament = await TournamentsRepo.get_by_id_for_update(session, locked_match.tournament_id)
        if tournament is None or tournament.type != TOURNAMENT_TYPE_DAILY_ELIMINATION:
            return 0, None, 0
        challenge = (
            await FriendChallengesRepo.get_by_id_for_update(session, locked_match.friend_challenge_id)
            if locked_match.friend_challenge_id is not None
            else None
        )
        winner_id, loser_id = (
            _resolve_winner_loser_for_timeout(challenge=challenge, match=locked_match)
            if challenge is not None
            else (int(locked_match.user_a), None)
        )
        if challenge is not None:
            _mark_challenge_forfeit(
                challenge=challenge,
                winner_id=winner_id,
                now_utc_value=now_utc_value,
            )
        locked_match.match_timeout_task_id = None
        settled = await settle_pending_match_from_duel(
            session,
            match=locked_match,
            now_utc=now_utc_value,
        )
        if not settled:
            return 0, None, 0
        transition = await on_elimination_match_complete(
            session,
            match_id=locked_match.id,
            winner_id=winner_id,
            loser_id=loser_id,
            now_utc=now_utc_value,
        )
        return 1, loser_id, int(transition.get("tournament_completed", 0))


async def run_elimination_match_timeout_async(*, match_id: str) -> dict[str, int]:
    try:
        parsed_match_id = UUID(match_id)
    except ValueError:
        return {"processed": 0, "settled_total": 0, "tournament_completed": 0}
    now_utc_value = now_utc()
    async with SessionLocal.begin() as session:
        match = await TournamentMatchesRepo.get_by_id_for_update(session, parsed_match_id)
        if match is None or match.status != TOURNAMENT_MATCH_STATUS_PENDING:
            return {"processed": 0, "settled_total": 0, "tournament_completed": 0}
    settled, _loser_id, completed = await _settle_single_pending_match(
        match=match,
        now_utc_value=now_utc_value,
    )
    return {
        "processed": 1,
        "settled_total": int(settled),
        "tournament_completed": int(completed),
    }


async def run_daily_elimination_final_deadline_async() -> dict[str, int]:
    now_utc_value = now_utc()
    tournaments_processed = 0
    matches_settled = 0
    tournaments_completed = 0

    async with SessionLocal.begin() as session:
        due_tournaments = await TournamentsRepo.list_due_round_deadline_for_update(
            session,
            now_utc=now_utc_value,
            limit=100,
            tournament_type=TOURNAMENT_TYPE_DAILY_ELIMINATION,
        )
        tournament_ids = [item.id for item in due_tournaments if item.status == "BRACKET_LIVE"]

    for tournament_id in tournament_ids:
        tournaments_processed += 1
        guard = 0
        while guard < 5000:
            guard += 1
            async with SessionLocal.begin() as session:
                pending_matches = await TournamentMatchesRepo.list_pending_for_tournament_for_update(
                    session,
                    tournament_id=tournament_id,
                )
                pending_snapshot = [match for match in pending_matches]
            if not pending_snapshot:
                break
            progress = False
            for pending_match in pending_snapshot:
                settled, _loser_id, completed = await _settle_single_pending_match(
                    match=pending_match,
                    now_utc_value=now_utc_value,
                )
                if settled > 0:
                    progress = True
                    matches_settled += 1
                if completed > 0:
                    tournaments_completed += 1
                    progress = False
                    break
            if not progress:
                break

    return {
        "processed": 1,
        "tournaments_processed": tournaments_processed,
        "matches_settled": matches_settled,
        "tournaments_completed": tournaments_completed,
    }
