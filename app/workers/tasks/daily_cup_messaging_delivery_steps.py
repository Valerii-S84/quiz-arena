from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workers.tasks.daily_cup_messaging_delivery_types import (
    DailyCupDeliveryContext,
    DailyCupDeliveryDependencies,
    DailyCupDeliveryState,
)


@dataclass(frozen=True, slots=True)
class DailyCupDeliveryRun:
    rounds_total: int
    happened_at: Any
    task_name: str
    content_version: str


@dataclass(frozen=True, slots=True)
class DailyCupUserDelivery:
    user_id: int
    chat_id: int | None
    existing_message_id: int | None
    target: Any
    text: str
    keyboard: Any


def build_delivery_target(
    *,
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    run: DailyCupDeliveryRun,
    user_id: int,
    chat_id: int | None,
    existing_message_id: int | None,
    fallback: bool = False,
) -> Any:
    operation = (
        dependencies.fallback_delivery_operation(existing_message_id)
        if fallback
        else dependencies.delivery_operation(existing_message_id)
    )
    return dependencies.daily_cup_round_delivery_target(
        flow="daily_cup_round_messaging",
        task_name=run.task_name,
        correlation_id=str(context.tournament.id),
        user_id=user_id,
        chat_id=chat_id,
        delivery_operation=operation,
        content_version=run.content_version,
        tournament_status=str(context.tournament.status),
        current_round=int(context.tournament.current_round),
        pending_replay_safe=existing_message_id is not None and not fallback,
    )


async def _record_fallback_failure(
    *,
    dependencies: DailyCupDeliveryDependencies,
    state: DailyCupDeliveryState,
    run: DailyCupDeliveryRun,
    delivery: DailyCupUserDelivery,
    fallback_target: Any,
    exc: Exception,
) -> None:
    state.failed += 1
    failure = await dependencies.mark_telegram_delivery_failed(
        idempotency_key=fallback_target.idempotency_key,
        happened_at=run.happened_at,
        exc=exc,
    )
    await dependencies.fallback_delivery.mark_original_edit_failed_after_fallback_failure(
        idempotency_key=delivery.target.idempotency_key,
        happened_at=run.happened_at,
        failure=failure,
    )


async def send_fallback_message(
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    state: DailyCupDeliveryState,
    run: DailyCupDeliveryRun,
    delivery: DailyCupUserDelivery,
) -> None:
    fallback_target = build_delivery_target(
        context=context,
        dependencies=dependencies,
        run=run,
        user_id=delivery.user_id,
        chat_id=delivery.chat_id,
        existing_message_id=delivery.existing_message_id,
        fallback=True,
    )
    decision = await dependencies.prepare_telegram_delivery(
        target=fallback_target, happened_at=run.happened_at
    )
    if not decision.should_send:
        state.skipped += 1
        await dependencies.fallback_delivery.record_original_edit_skipped_after_fallback_skip(
            target=delivery.target,
            happened_at=run.happened_at,
            fallback_status=decision.status,
        )
        return
    await dependencies.begin_telegram_delivery_dispatch(decision, happened_at=run.happened_at)
    try:
        message = await context.bot.send_message(
            chat_id=delivery.chat_id,
            text=delivery.text,
            reply_markup=delivery.keyboard,
        )
    except Exception as exc:
        await _record_fallback_failure(
            dependencies=dependencies,
            state=state,
            run=run,
            delivery=delivery,
            fallback_target=fallback_target,
            exc=exc,
        )
        return
    message_id = await dependencies.persist_daily_cup_sent_message(
        fallback_target,
        context.tournament.id,
        delivery.user_id,
        message,
        run.happened_at,
        replace_existing=True,
    )
    await dependencies.fallback_delivery.record_original_edit_skipped_after_fallback_success(
        target=delivery.target,
        happened_at=run.happened_at,
    )
    state.sent += 1
    state.replaced_message_ids[delivery.user_id] = message_id


__all__ = [
    "DailyCupDeliveryRun",
    "DailyCupUserDelivery",
    "build_delivery_target",
    "send_fallback_message",
]
