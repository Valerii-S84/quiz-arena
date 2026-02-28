from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED
from app.game.tournaments.lifecycle import close_expired_registration, settle_round_and_advance
from app.workers.tasks.tournaments_config import DEADLINE_BATCH_SIZE, ROUND_DURATION_HOURS
from app.workers.tasks.tournaments_messaging import enqueue_private_tournament_round_messaging
from app.workers.tasks.tournaments_proof_cards import enqueue_private_tournament_proof_cards

logger = structlog.get_logger("app.workers.tasks.tournaments")


async def _emit_round_events(
    *,
    now_utc: datetime,
    started_tournament_ids: list[str],
    completed_tournament_ids: list[str],
) -> None:
    if not started_tournament_ids and not completed_tournament_ids:
        return
    async with SessionLocal.begin() as session:
        for tournament_id in started_tournament_ids:
            await emit_analytics_event(
                session,
                event_type="private_tournament_round_started",
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc,
                user_id=None,
                payload={"tournament_id": tournament_id},
            )
        for tournament_id in completed_tournament_ids:
            await emit_analytics_event(
                session,
                event_type="private_tournament_completed",
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc,
                user_id=None,
                payload={"tournament_id": tournament_id},
            )


async def run_private_tournament_rounds_async(
    *,
    batch_size: int = DEADLINE_BATCH_SIZE,
    round_duration_hours: int = ROUND_DURATION_HOURS,
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    resolved_batch_size = max(1, int(batch_size))

    registration_closed_total = 0
    rounds_started_total = 0
    tournaments_completed_total = 0
    matches_settled_total = 0
    matches_created_total = 0
    started_ids: list[str] = []
    completed_ids: list[str] = []

    async with SessionLocal.begin() as session:
        due_registration = await TournamentsRepo.list_due_registration_close_for_update(
            session,
            now_utc=now_utc,
            limit=resolved_batch_size,
        )
        for tournament in due_registration:
            if await close_expired_registration(session, tournament=tournament):
                registration_closed_total += 1

        due_rounds = await TournamentsRepo.list_due_round_deadline_for_update(
            session,
            now_utc=now_utc,
            limit=resolved_batch_size,
        )
        for tournament in due_rounds:
            transition = await settle_round_and_advance(
                session,
                tournament=tournament,
                now_utc=now_utc,
                round_duration_hours=round_duration_hours,
            )
            rounds_started_total += int(transition["round_started"])
            tournaments_completed_total += int(transition["tournament_completed"])
            matches_settled_total += int(transition["matches_settled"])
            matches_created_total += int(transition["matches_created"])
            if int(transition["round_started"]) > 0:
                started_ids.append(str(tournament.id))
            if tournament.status == TOURNAMENT_STATUS_COMPLETED:
                completed_ids.append(str(tournament.id))

    await _emit_round_events(
        now_utc=now_utc,
        started_tournament_ids=started_ids,
        completed_tournament_ids=completed_ids,
    )
    for tournament_id in started_ids:
        enqueue_private_tournament_round_messaging(tournament_id=tournament_id)
    for tournament_id in completed_ids:
        enqueue_private_tournament_round_messaging(tournament_id=tournament_id)
        enqueue_private_tournament_proof_cards(tournament_id=tournament_id)

    result = {
        "batch_size": resolved_batch_size,
        "registration_closed_total": registration_closed_total,
        "rounds_started_total": rounds_started_total,
        "tournaments_completed_total": tournaments_completed_total,
        "matches_settled_total": matches_settled_total,
        "matches_created_total": matches_created_total,
        "round_messages_enqueued_total": len(started_ids) + len(completed_ids),
        "proof_cards_enqueued_total": len(completed_ids),
    }
    logger.info("private_tournament_rounds_processed", **result)
    return result
