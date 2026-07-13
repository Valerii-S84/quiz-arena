from __future__ import annotations

from typing import cast

from app.workers.tasks.tournaments_messaging_delivery_types import (
    TournamentRoundDeliveryContext,
    TournamentRoundDeliveryState,
    TournamentRoundMessageAttempt,
)


async def send_initial_round_message(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> None:
    try:
        message = await delivery_context.bot.send_message(
            chat_id=attempt.chat_id,
            text=attempt.text,
            reply_markup=attempt.keyboard,
        )
    except Exception as exc:
        state.failed += 1
        await delivery_context.operations.mark_failed(
            idempotency_key=attempt.target.idempotency_key,
            happened_at=delivery_context.happened_at,
            exc=exc,
        )
        return
    message_id = await delivery_context.operations.persist_initial_message(
        attempt.target,
        delivery_context.request.context.parsed_tournament_id,
        attempt.user_id,
        message,
        delivery_context.happened_at,
    )
    state.sent += 1
    state.new_message_ids[attempt.user_id] = message_id


def _build_fallback_target(
    delivery_context: TournamentRoundDeliveryContext,
    attempt: TournamentRoundMessageAttempt,
):
    operations = delivery_context.operations
    existing_message_id = cast(int, attempt.existing_message_id)
    return operations.build_target(
        delivery_context=delivery_context,
        user_id=attempt.user_id,
        chat_id=attempt.chat_id,
        delivery_operation=operations.fallback_delivery_operation(existing_message_id),
        pending_replay_safe=False,
    )


async def _send_fallback_round_message(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> None:
    operations = delivery_context.operations
    context = delivery_context.request.context
    fallback_target = _build_fallback_target(delivery_context, attempt)
    fallback_delivery = await operations.prepare_fallback_delivery(
        target=fallback_target,
        happened_at=delivery_context.happened_at,
    )
    if not fallback_delivery.should_send:
        state.skipped += 1
        await operations.record_original_skipped(
            target=attempt.target,
            happened_at=delivery_context.happened_at,
            fallback_status=fallback_delivery.status,
        )
        return
    await operations.begin_fallback_dispatch(
        fallback_delivery,
        happened_at=delivery_context.happened_at,
    )
    try:
        message = await delivery_context.bot.send_message(
            chat_id=attempt.chat_id,
            text=attempt.text,
            reply_markup=attempt.keyboard,
        )
    except Exception as exc:
        state.failed += 1
        await operations.mark_fallback_and_original_failed(
            fallback_idempotency_key=fallback_target.idempotency_key,
            original_idempotency_key=attempt.target.idempotency_key,
            happened_at=delivery_context.happened_at,
            exc=exc,
        )
        return
    message_id = await operations.persist_replacement_message(
        fallback_target,
        context.parsed_tournament_id,
        attempt.user_id,
        message,
        delivery_context.happened_at,
        replace_existing=True,
        original_target=attempt.target,
    )
    state.sent += 1
    state.replaced_message_ids[attempt.user_id] = message_id


async def edit_or_replace_round_message(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> None:
    try:
        await delivery_context.bot.edit_message_text(
            chat_id=attempt.chat_id,
            message_id=int(cast(int, attempt.existing_message_id)),
            text=attempt.text,
            reply_markup=attempt.keyboard,
        )
    except Exception as exc:
        if delivery_context.request.is_message_not_modified_error_fn(exc):
            await delivery_context.operations.mark_sent(
                idempotency_key=attempt.target.idempotency_key,
                happened_at=delivery_context.happened_at,
            )
            state.edited += 1
            return
        await _send_fallback_round_message(
            delivery_context=delivery_context,
            state=state,
            attempt=attempt,
        )
        return
    await delivery_context.operations.mark_sent(
        idempotency_key=attempt.target.idempotency_key,
        happened_at=delivery_context.happened_at,
    )
    state.edited += 1


__all__ = ["edit_or_replace_round_message", "send_initial_round_message"]
