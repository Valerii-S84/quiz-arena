from __future__ import annotations

from typing import cast

from app.workers.tasks.tournaments_message_delivery_persistence import (
    PrivateTournamentStandingsFence,
)
from app.workers.tasks.tournaments_messaging_delivery_targets import (
    SKIP_CODE_EDIT_REPLACED_BY_SEND,
)
from app.workers.tasks.tournaments_messaging_delivery_types import (
    TournamentRoundDeliveryContext,
    TournamentRoundDeliveryState,
    TournamentRoundMessageAttempt,
)


def _persistence_fence(
    delivery_context: TournamentRoundDeliveryContext,
    attempt: TournamentRoundMessageAttempt,
) -> PrivateTournamentStandingsFence:
    tournament = delivery_context.request.context.tournament
    return PrivateTournamentStandingsFence(
        tournament_id=delivery_context.request.context.parsed_tournament_id,
        user_id=attempt.user_id,
        expected_message_id=attempt.existing_message_id,
        expected_status=str(tournament.status),
        expected_round=int(tournament.current_round),
    )


async def _prepare_delivery(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> bool:
    preparation = await delivery_context.operations.prepare_delivery(attempt.target)
    if preparation.should_send:
        return True
    state.skipped += 1
    return False


async def _record_delivery_exception(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    target: object,
    exc: Exception,
) -> str:
    return await delivery_context.operations.record_delivery_failure(target, exc)


async def send_initial_round_message(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> None:
    if not await _prepare_delivery(
        delivery_context=delivery_context,
        state=state,
        attempt=attempt,
    ):
        return
    try:
        message = await delivery_context.bot.send_message(
            chat_id=attempt.chat_id,
            text=attempt.text,
            reply_markup=attempt.keyboard,
        )
        message_id = await delivery_context.operations.persist_initial_message(
            attempt.target,
            _persistence_fence(delivery_context, attempt),
            message,
            delivery_context.happened_at,
        )
    except Exception as exc:
        status = await _record_delivery_exception(
            delivery_context=delivery_context,
            target=attempt.target,
            exc=exc,
        )
        if status == "FAILED":
            state.failed += 1
        else:
            state.skipped += 1
        return
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
    edit_error: Exception,
) -> None:
    operations = delivery_context.operations
    fallback_target = _build_fallback_target(delivery_context, attempt)
    fallback_attempt = TournamentRoundMessageAttempt(
        user_id=attempt.user_id,
        chat_id=attempt.chat_id,
        existing_message_id=attempt.existing_message_id,
        target=fallback_target,
        text=attempt.text,
        keyboard=attempt.keyboard,
    )
    if not await _prepare_delivery(
        delivery_context=delivery_context,
        state=state,
        attempt=fallback_attempt,
    ):
        await operations.record_delivery_skipped(
            attempt.target,
            failure_code=SKIP_CODE_EDIT_REPLACED_BY_SEND,
            failure_reason="fallback send skipped after edit failed",
        )
        return
    try:
        message = await delivery_context.bot.send_message(
            chat_id=attempt.chat_id,
            text=attempt.text,
            reply_markup=attempt.keyboard,
        )
        message_id = await operations.persist_replacement_message(
            fallback_target,
            _persistence_fence(delivery_context, attempt),
            message,
            delivery_context.happened_at,
            original_target=attempt.target,
        )
    except Exception as exc:
        fallback_status = await _record_delivery_exception(
            delivery_context=delivery_context,
            target=fallback_target,
            exc=exc,
        )
        await _record_delivery_exception(
            delivery_context=delivery_context,
            target=attempt.target,
            exc=edit_error,
        )
        if fallback_status == "FAILED":
            state.failed += 1
        else:
            state.skipped += 1
        return
    state.sent += 1
    state.replaced_message_ids[attempt.user_id] = message_id


async def _persist_successful_edit(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> None:
    message_id = await delivery_context.operations.persist_edited_message(
        attempt.target,
        _persistence_fence(delivery_context, attempt),
        int(cast(int, attempt.existing_message_id)),
        delivery_context.happened_at,
    )
    state.edited += 1
    state.new_message_ids.pop(attempt.user_id, None)
    state.replaced_message_ids.pop(attempt.user_id, None)
    if message_id != attempt.existing_message_id:
        state.replaced_message_ids[attempt.user_id] = message_id


async def edit_or_replace_round_message(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    attempt: TournamentRoundMessageAttempt,
) -> None:
    if not await _prepare_delivery(
        delivery_context=delivery_context,
        state=state,
        attempt=attempt,
    ):
        return
    try:
        await delivery_context.bot.edit_message_text(
            chat_id=attempt.chat_id,
            message_id=int(cast(int, attempt.existing_message_id)),
            text=attempt.text,
            reply_markup=attempt.keyboard,
        )
    except Exception as exc:
        if delivery_context.request.is_message_not_modified_error_fn(exc):
            await _persist_successful_edit(
                delivery_context=delivery_context,
                state=state,
                attempt=attempt,
            )
            return
        await _send_fallback_round_message(
            delivery_context=delivery_context,
            state=state,
            attempt=attempt,
            edit_error=exc,
        )
        return
    await _persist_successful_edit(
        delivery_context=delivery_context,
        state=state,
        attempt=attempt,
    )


__all__ = ["edit_or_replace_round_message", "send_initial_round_message"]
