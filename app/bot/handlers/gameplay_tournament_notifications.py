from __future__ import annotations


def enqueue_tournament_round_messaging(*, tournament_id: str) -> None:
    from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging
    from app.workers.tasks.tournaments_messaging import enqueue_private_tournament_round_messaging

    enqueue_private_tournament_round_messaging(tournament_id=tournament_id)
    enqueue_daily_cup_round_messaging(tournament_id=tournament_id)
