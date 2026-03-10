from __future__ import annotations


def handle_daily_cup_completion_followups(
    *,
    is_completed: bool,
    enqueue_completion_followups: bool,
    allow_completion_followups: bool,
    tournament_id: str,
    registration_deadline,
    logger,
) -> None:
    if not is_completed or not enqueue_completion_followups:
        return
    if allow_completion_followups:
        from app.workers.tasks.daily_cup_nonfinishers_summary import (
            enqueue_daily_cup_nonfinishers_summary,
        )
        from app.workers.tasks.daily_cup_proof_cards import enqueue_daily_cup_proof_cards

        enqueue_daily_cup_proof_cards(tournament_id=tournament_id, delay_seconds=2)
        enqueue_daily_cup_nonfinishers_summary(tournament_id=tournament_id)
        return
    logger.info(
        "daily_cup_completion_followups_skipped_stale_tournament",
        tournament_id=tournament_id,
        registration_deadline=(
            registration_deadline.isoformat() if registration_deadline is not None else None
        ),
    )
