from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_MATCH_STATUS_WALKOVER,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.lifecycle import settle_round_and_advance
from app.workers.tasks.daily_cup_match_results import send_daily_cup_match_result_messages
from app.workers.tasks.daily_cup_core import emit_daily_cup_events, now_utc
from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging

logger = structlog.get_logger("app.workers.tasks.daily_cup")


def _now_utc():
    return now_utc()


@dataclass(frozen=True, slots=True)
class WalkoverNotification:
    tournament_id: UUID
    round_no: int
    user_a: int
    user_b: int
    user_a_points: int
    user_b_points: int
    rounds_total: int
    next_round_deadline: datetime | None


def _match_scores_from_challenge(*, match, challenge) -> tuple[int, int]:
    creator_user_id = int(challenge.creator_user_id)
    creator_score = int(challenge.creator_score)
    opponent_score = int(challenge.opponent_score)
    if int(match.user_a) == creator_user_id:
        return creator_score, opponent_score
    return opponent_score, creator_score


def enqueue_daily_cup_proof_cards(*, tournament_id: str) -> None:
    from app.workers.tasks.daily_cup_proof_cards import enqueue_daily_cup_proof_cards as _enqueue

    _enqueue(tournament_id=tournament_id)


def enqueue_daily_cup_nonfinishers_summary(*, tournament_id: str) -> None:
    from app.workers.tasks.daily_cup_nonfinishers_summary import (
        enqueue_daily_cup_nonfinishers_summary as _enqueue,
    )

    _enqueue(tournament_id=tournament_id)


async def advance_daily_cup_rounds_async() -> dict[str, int]:
    now_utc_value = _now_utc()
    rounds_started_total = 0
    tournaments_completed_total = 0
    matches_settled_total = 0
    matches_created_total = 0
    started_ids: list[tuple[str, int]] = []
    completed_ids: list[str] = []
    walkover_notifications: list[WalkoverNotification] = []
    events: list[dict[str, object]] = []

    async with SessionLocal.begin() as session:
        due_rounds = await TournamentsRepo.list_due_round_deadline_for_update(
            session,
            now_utc=now_utc_value,
            limit=50,
            tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        )
        for tournament in due_rounds:
            round_before = max(1, int(tournament.current_round))
            pending_round_matches = await TournamentMatchesRepo.list_by_tournament_round_for_update(
                session,
                tournament_id=tournament.id,
                round_no=round_before,
            )
            pending_match_ids = {
                match.id
                for match in pending_round_matches
                if match.status == TOURNAMENT_MATCH_STATUS_PENDING
            }
            transition = await settle_round_and_advance(
                session,
                tournament=tournament,
                now_utc=now_utc_value,
            )
            settled_count = int(transition["matches_settled"])
            started_count = int(transition["round_started"])
            completed_count = int(transition["tournament_completed"])
            matches_settled_total += settled_count
            matches_created_total += int(transition["matches_created"])
            rounds_started_total += started_count
            tournaments_completed_total += completed_count

            for _ in range(settled_count):
                events.append(
                    {
                        "event_type": "daily_cup_match_completed",
                        "payload": {"tournament_id": str(tournament.id), "round_no": round_before},
                    }
                )
            if started_count > 0:
                started_ids.append((str(tournament.id), int(tournament.current_round)))
                events.append(
                    {
                        "event_type": "daily_cup_round_started",
                        "payload": {
                            "tournament_id": str(tournament.id),
                            "round_no": int(tournament.current_round),
                        },
                    }
                )
            if completed_count > 0 or tournament.status == TOURNAMENT_STATUS_COMPLETED:
                completed_ids.append(str(tournament.id))
            if settled_count > 0 and pending_match_ids:
                settled_round_matches = await TournamentMatchesRepo.list_by_tournament_round_for_update(
                    session,
                    tournament_id=tournament.id,
                    round_no=round_before,
                )
                for match in settled_round_matches:
                    if (
                        match.id not in pending_match_ids
                        or match.status != TOURNAMENT_MATCH_STATUS_WALKOVER
                        or match.user_b is None
                        or match.winner_id is None
                        or match.friend_challenge_id is None
                    ):
                        continue
                    challenge = await FriendChallengesRepo.get_by_id(session, match.friend_challenge_id)
                    if challenge is None:
                        continue
                    user_a_points, user_b_points = _match_scores_from_challenge(
                        match=match,
                        challenge=challenge,
                    )
                    walkover_notifications.append(
                        WalkoverNotification(
                            tournament_id=match.tournament_id,
                            round_no=int(match.round_no),
                            user_a=int(match.user_a),
                            user_b=int(match.user_b),
                            user_a_points=user_a_points,
                            user_b_points=user_b_points,
                            rounds_total=max(1, int(challenge.total_rounds)),
                            next_round_deadline=tournament.round_deadline,
                        )
                    )

    await emit_daily_cup_events(now_utc_value=now_utc_value, events=events)
    for notification in walkover_notifications:
        async with SessionLocal.begin() as session:
            await send_daily_cup_match_result_messages(
                session,
                tournament_id=notification.tournament_id,
                round_no=notification.round_no,
                user_a=notification.user_a,
                user_b=notification.user_b,
                user_a_points=notification.user_a_points,
                user_b_points=notification.user_b_points,
                rounds_total=notification.rounds_total,
                next_round_deadline=notification.next_round_deadline,
            )
    for tournament_id, _round_no in started_ids:
        enqueue_daily_cup_round_messaging(tournament_id=tournament_id)
    for tournament_id in completed_ids:
        enqueue_daily_cup_round_messaging(
            tournament_id=tournament_id,
            enqueue_completion_followups=True,
        )

    result = {
        "processed": 1,
        "rounds_started_total": rounds_started_total,
        "tournaments_completed_total": tournaments_completed_total,
        "matches_settled_total": matches_settled_total,
        "matches_created_total": matches_created_total,
    }
    logger.info("daily_cup_rounds_processed", **result)
    return result
