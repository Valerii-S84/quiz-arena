from __future__ import annotations

import structlog

from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED, TOURNAMENT_TYPE_DAILY_ARENA
from app.game.tournaments.lifecycle import settle_round_and_advance
from app.workers.tasks.daily_cup_core import emit_daily_cup_events, now_utc
from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging
from app.workers.tasks.daily_cup_proof_cards import enqueue_daily_cup_proof_cards

logger = structlog.get_logger("app.workers.tasks.daily_cup")


async def advance_daily_cup_rounds_async() -> dict[str, int]:
    now_utc_value = now_utc()
    rounds_started_total = 0
    tournaments_completed_total = 0
    matches_settled_total = 0
    matches_created_total = 0
    started_ids: list[tuple[str, int]] = []
    completed_ids: list[str] = []
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

    await emit_daily_cup_events(now_utc_value=now_utc_value, events=events)
    for tournament_id, _round_no in started_ids:
        enqueue_daily_cup_round_messaging(tournament_id=tournament_id)
    for tournament_id in completed_ids:
        enqueue_daily_cup_round_messaging(tournament_id=tournament_id)
        enqueue_daily_cup_proof_cards(tournament_id=tournament_id)

    result = {
        "processed": 1,
        "rounds_started_total": rounds_started_total,
        "tournaments_completed_total": tournaments_completed_total,
        "matches_settled_total": matches_settled_total,
        "matches_created_total": matches_created_total,
    }
    logger.info("daily_cup_rounds_processed", **result)
    return result
