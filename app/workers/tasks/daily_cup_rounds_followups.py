from __future__ import annotations

from typing import Any

from app.db.session import SessionLocal


async def send_daily_cup_walkover_notifications(
    *,
    notifications: list[Any],
    send_match_result_messages_fn: Any,
) -> None:
    for notification in notifications:
        async with SessionLocal.begin() as session:
            await send_match_result_messages_fn(
                session,
                tournament_id=notification.tournament_id,
                round_no=notification.round_no,
                user_a=notification.user_a,
                user_b=notification.user_b,
                user_a_points=notification.user_a_points,
                user_b_points=notification.user_b_points,
                rounds_total=notification.rounds_total,
                tournament_registration_deadline=notification.tournament_registration_deadline,
                next_round_start_time=notification.next_round_start_time,
            )


def enqueue_daily_cup_completion_messaging(
    *,
    tournament_ids: list[str],
    enqueue_round_messaging_fn: Any,
) -> None:
    for tournament_id in tournament_ids:
        enqueue_round_messaging_fn(
            tournament_id=tournament_id,
            enqueue_completion_followups=True,
        )


__all__ = [
    "enqueue_daily_cup_completion_messaging",
    "send_daily_cup_walkover_notifications",
]
