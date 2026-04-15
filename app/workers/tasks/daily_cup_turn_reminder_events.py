from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID


async def store_reminder_events(
    *,
    sent_user_ids_by_tournament: dict[UUID, list[int]],
    event_type: str,
    happened_at: datetime,
    store_push_sent_events_fn: Callable[..., Awaitable[None]],
    logger,
) -> None:
    for tournament_id, sent_user_ids in sent_user_ids_by_tournament.items():
        try:
            await store_push_sent_events_fn(
                event_type=event_type,
                tournament_id=tournament_id,
                user_ids=sent_user_ids,
                happened_at=happened_at,
            )
        except Exception as exc:
            logger.warning(
                "daily_cup_turn_reminder_event_store_failed",
                tournament_id=str(tournament_id),
                sent_total=len(sent_user_ids),
                error_type=type(exc).__name__,
            )


__all__ = ["store_reminder_events"]
