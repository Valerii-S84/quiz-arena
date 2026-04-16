from __future__ import annotations

import structlog

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import (
    TOURNAMENT_MATCH_STATUS_PENDING,
    TOURNAMENT_MATCH_STATUS_WALKOVER,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_TYPE_DAILY_ARENA,
    daily_cup_max_rounds_for_participants,
)
from app.game.tournaments.lifecycle import settle_round_and_advance
from app.workers.tasks.daily_cup_core import emit_daily_cup_events, now_utc
from app.workers.tasks.daily_cup_match_results import send_daily_cup_match_result_messages
from app.workers.tasks.daily_cup_rounds_followups import (
    enqueue_daily_cup_completion_messaging,
    send_daily_cup_walkover_notifications,
)
from app.workers.tasks.daily_cup_rounds_processing import (
    advance_due_daily_cup_rounds,
    match_scores_from_challenge,
)

logger = structlog.get_logger("app.workers.tasks.daily_cup")


def _now_utc():
    return now_utc()


def _match_scores_from_challenge(*, match, challenge) -> tuple[int, int]:
    return match_scores_from_challenge(match=match, challenge=challenge)


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
    async with SessionLocal.begin() as session:
        outcome = await advance_due_daily_cup_rounds(
            session=session,
            now_utc_value=now_utc_value,
            tournaments_repo=TournamentsRepo,
            participants_repo=TournamentParticipantsRepo,
            matches_repo=TournamentMatchesRepo,
            challenges_repo=FriendChallengesRepo,
            settle_round_and_advance_fn=settle_round_and_advance,
            tournament_type_daily_arena=TOURNAMENT_TYPE_DAILY_ARENA,
            pending_match_status=TOURNAMENT_MATCH_STATUS_PENDING,
            walkover_match_status=TOURNAMENT_MATCH_STATUS_WALKOVER,
            tournament_completed_status=TOURNAMENT_STATUS_COMPLETED,
            max_rounds_fn=daily_cup_max_rounds_for_participants,
        )

    await emit_daily_cup_events(now_utc_value=now_utc_value, events=outcome.events)
    await send_daily_cup_walkover_notifications(
        notifications=outcome.walkover_notifications,
        send_match_result_messages_fn=send_daily_cup_match_result_messages,
    )
    from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging

    enqueue_daily_cup_completion_messaging(
        tournament_ids=outcome.completed_ids,
        enqueue_round_messaging_fn=enqueue_daily_cup_round_messaging,
    )

    result = {
        "processed": 1,
        "rounds_started_total": outcome.rounds_started_total,
        "tournaments_completed_total": outcome.tournaments_completed_total,
        "matches_settled_total": outcome.matches_settled_total,
        "matches_created_total": outcome.matches_created_total,
    }
    logger.info("daily_cup_rounds_processed", **result)
    return result
