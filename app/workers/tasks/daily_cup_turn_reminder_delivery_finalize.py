from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.workers.tasks.daily_cup_turn_reminder_delivery_types import (
    ReminderBatch,
    ReminderDeliveryResult,
)


@dataclass(frozen=True, slots=True)
class ReminderDeliveryFinalizationDependencies:
    session_factory: Any
    mark_reminders_notified: Callable[..., Awaitable[None]]
    store_events: Callable[..., Awaitable[None]]
    store_push_sent_events: Callable[..., Awaitable[None]]
    logger: Any


async def finalize_delivered_reminders(
    *,
    batch: ReminderBatch,
    delivery_result: ReminderDeliveryResult,
    happened_at: datetime,
    event_type: str,
    dependencies: ReminderDeliveryFinalizationDependencies,
) -> None:
    completed_ids = batch.challenge_ids - delivery_result.failed_challenge_ids
    await _mark_delivered_reminder_candidates(
        batch=batch,
        completed_ids=completed_ids,
        delivered_at=happened_at,
        dependencies=dependencies,
    )
    await dependencies.store_events(
        sent_user_ids_by_tournament=delivery_result.sent_user_ids_by_tournament,
        event_type=event_type,
        happened_at=happened_at,
        store_push_sent_events_fn=dependencies.store_push_sent_events,
        logger=dependencies.logger,
    )
    if delivery_result.system_errors:
        raise delivery_result.system_errors[0]


async def _mark_delivered_reminder_candidates(
    *,
    batch: ReminderBatch,
    completed_ids: set[str],
    delivered_at: datetime,
    dependencies: ReminderDeliveryFinalizationDependencies,
) -> None:
    if not completed_ids:
        return
    async with dependencies.session_factory.begin() as session:
        await dependencies.mark_reminders_notified(
            session,
            challenge_ids={UUID(challenge_id) for challenge_id in completed_ids},
            notified_at=delivered_at,
        )
    for challenge in batch.challenge_rows:
        if str(challenge.id) in completed_ids:
            challenge.expires_last_chance_notified_at = delivered_at
            challenge.updated_at = delivered_at
