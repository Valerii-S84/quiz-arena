from __future__ import annotations

from typing import Any

from app.workers.tasks.daily_cup_messaging_delivery_content import build_daily_cup_message_payload
from app.workers.tasks.daily_cup_messaging_delivery_steps import (
    DailyCupDeliveryRun,
    DailyCupUserDelivery,
    build_delivery_target,
    send_fallback_message,
)
from app.workers.tasks.daily_cup_messaging_delivery_types import (
    DailyCupDeliveryContext,
    DailyCupDeliveryDependencies,
    DailyCupDeliveryState,
)


async def _send_new_message(
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    state: DailyCupDeliveryState,
    run: DailyCupDeliveryRun,
    delivery: DailyCupUserDelivery,
) -> None:
    try:
        message = await context.bot.send_message(
            chat_id=delivery.chat_id,
            text=delivery.text,
            reply_markup=delivery.keyboard,
        )
    except Exception as exc:
        state.failed += 1
        await dependencies.mark_telegram_delivery_failed(
            idempotency_key=delivery.target.idempotency_key,
            happened_at=run.happened_at,
            exc=exc,
        )
        return
    message_id = await dependencies.persist_daily_cup_sent_message(
        delivery.target,
        context.tournament.id,
        delivery.user_id,
        message,
        run.happened_at,
    )
    state.sent += 1
    state.new_message_ids[delivery.user_id] = message_id


async def _edit_existing_message(
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    state: DailyCupDeliveryState,
    run: DailyCupDeliveryRun,
    delivery: DailyCupUserDelivery,
) -> None:
    try:
        await context.bot.edit_message_text(
            chat_id=delivery.chat_id,
            message_id=int(delivery.existing_message_id or 0),
            text=delivery.text,
            reply_markup=delivery.keyboard,
        )
    except Exception as exc:
        if dependencies.is_message_not_modified_error(exc):
            await dependencies.mark_telegram_delivery_sent(
                idempotency_key=delivery.target.idempotency_key,
                happened_at=run.happened_at,
            )
            state.edited += 1
            return
        await send_fallback_message(context, dependencies, state, run, delivery)
        return
    await dependencies.mark_telegram_delivery_sent(
        idempotency_key=delivery.target.idempotency_key,
        happened_at=run.happened_at,
    )
    state.edited += 1


async def _deliver_to_user(
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
    state: DailyCupDeliveryState,
    run: DailyCupDeliveryRun,
    user_id: int,
) -> None:
    chat_id = context.telegram_targets.get(user_id)
    existing_message_id = context.participant_rows[user_id].standings_message_id
    target = build_delivery_target(
        context=context,
        dependencies=dependencies,
        run=run,
        user_id=user_id,
        chat_id=chat_id,
        existing_message_id=existing_message_id,
    )
    text, keyboard = build_daily_cup_message_payload(
        context=context,
        dependencies=dependencies,
        rounds_total=run.rounds_total,
        user_id=user_id,
    )
    decision = await dependencies.prepare_telegram_delivery(
        target=target, happened_at=run.happened_at
    )
    if not decision.should_send:
        state.skipped += 1
        return
    await dependencies.begin_telegram_delivery_dispatch(decision, happened_at=run.happened_at)
    delivery = DailyCupUserDelivery(
        user_id=user_id,
        chat_id=chat_id,
        existing_message_id=existing_message_id,
        target=target,
        text=text,
        keyboard=keyboard,
    )
    if existing_message_id is None:
        await _send_new_message(context, dependencies, state, run, delivery)
        return
    await _edit_existing_message(context, dependencies, state, run, delivery)


async def deliver_daily_cup_messages_with_dependencies(
    *,
    context: DailyCupDeliveryContext,
    dependencies: DailyCupDeliveryDependencies,
) -> dict[str, Any]:
    state = DailyCupDeliveryState()
    run = DailyCupDeliveryRun(
        rounds_total=dependencies.daily_cup_max_rounds_for_participants(
            participants_total=context.participants_total
        ),
        happened_at=dependencies.happened_at(),
        task_name="daily_cup.run_daily_cup_round_messaging",
        content_version=dependencies.daily_cup_content_version(tournament=context.tournament),
    )
    for user_id in context.standings_user_ids:
        await _deliver_to_user(context, dependencies, state, run, user_id)
    return state.to_result(dependencies)
