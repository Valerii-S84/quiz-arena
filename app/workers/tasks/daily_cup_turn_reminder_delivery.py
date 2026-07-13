from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.services.telegram_delivery import (
    TelegramDeliveryTarget,
    begin_telegram_delivery_dispatch,
    build_delivery_idempotency_key,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)
from app.workers.tasks.daily_cup_turn_reminder_delivery_batch import ReminderBatchPreparationRequest
from app.workers.tasks.daily_cup_turn_reminder_delivery_batch import (
    _window_key as _batch_window_key,
)
from app.workers.tasks.daily_cup_turn_reminder_delivery_batch import (
    prepare_reminder_batch as prepare_reminder_batch_with_dependencies,
)
from app.workers.tasks.daily_cup_turn_reminder_delivery_runtime import (
    deliver_reminders_with_dependencies,
)
from app.workers.tasks.daily_cup_turn_reminder_delivery_target import (
    build_turn_reminder_delivery_target,
)
from app.workers.tasks.daily_cup_turn_reminder_delivery_types import (
    ReminderBatch,
    ReminderDeliveryDependencies,
    ReminderDeliveryResult,
    ReminderItem,
)


async def _prepare_delivery_decision(*, target: TelegramDeliveryTarget, happened_at: datetime):
    return await prepare_telegram_delivery(target=target, happened_at=happened_at)


async def _begin_delivery_dispatch(delivery: Any, *, happened_at: datetime):
    return await begin_telegram_delivery_dispatch(delivery, happened_at=happened_at)


async def prepare_reminder_batch(
    *,
    candidates: list[tuple[Any, Any]],
    now_utc_value: datetime,
    format_user_label_fn: Callable[..., str],
    list_users_by_ids: Callable[..., Awaitable[list[Any]]],
    session: Any,
    resolve_turn_reminder_users_fn: Callable[..., tuple[tuple[int, int], ...]],
    resolve_opponent_label_fn: Callable[..., str],
    format_deadline_fn: Callable[..., str],
) -> ReminderBatch:
    return await prepare_reminder_batch_with_dependencies(
        request=ReminderBatchPreparationRequest(
            candidates=candidates,
            now_utc_value=now_utc_value,
            format_user_label_fn=format_user_label_fn,
            list_users_by_ids=list_users_by_ids,
            session=session,
            resolve_turn_reminder_users_fn=resolve_turn_reminder_users_fn,
            resolve_opponent_label_fn=resolve_opponent_label_fn,
            format_deadline_fn=format_deadline_fn,
        )
    )


async def deliver_reminders(
    *,
    reminders: list[ReminderItem],
    build_bot_fn: Callable[[], Any],
    build_keyboard: Callable[..., object],
    build_text: Callable[..., str],
    logger: Any,
) -> ReminderDeliveryResult:
    dependencies = ReminderDeliveryDependencies(
        prepare_telegram_delivery=_prepare_delivery_decision,
        begin_telegram_delivery_dispatch=_begin_delivery_dispatch,
        mark_telegram_delivery_failed=mark_telegram_delivery_failed,
        mark_telegram_delivery_sent=mark_telegram_delivery_sent,
        build_delivery_idempotency_key=build_delivery_idempotency_key,
        happened_at=lambda: datetime.now(timezone.utc),
    )
    return await deliver_reminders_with_dependencies(
        reminders=reminders,
        build_bot_fn=build_bot_fn,
        build_keyboard=build_keyboard,
        build_text=build_text,
        logger=logger,
        dependencies=dependencies,
    )


def _turn_reminder_delivery_target(*, reminder: ReminderItem) -> TelegramDeliveryTarget:
    return build_turn_reminder_delivery_target(
        reminder=reminder,
        build_delivery_idempotency_key_fn=build_delivery_idempotency_key,
    )


def _window_key(value: datetime | None) -> str:
    return _batch_window_key(value)


__all__ = "ReminderBatch ReminderDeliveryResult ReminderItem deliver_reminders prepare_reminder_batch".split()
