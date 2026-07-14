from __future__ import annotations

from datetime import datetime, timezone

from app.workers.tasks.tournaments_messaging_delivery_steps import (
    edit_or_replace_round_message,
    send_initial_round_message,
)
from app.workers.tasks.tournaments_messaging_delivery_types import (
    TournamentRoundDeliveryContext,
    TournamentRoundDeliveryOperations,
    TournamentRoundDeliveryRequest,
    TournamentRoundDeliveryResult,
    TournamentRoundDeliveryState,
    TournamentRoundMessageAttempt,
)


def _build_round_payload(
    delivery_context: TournamentRoundDeliveryContext,
    user_id: int,
) -> tuple[str, object]:
    request = delivery_context.request
    return delivery_context.operations.build_payload(
        request=request,
        user_id=user_id,
    )


async def _deliver_user_message(
    *,
    delivery_context: TournamentRoundDeliveryContext,
    state: TournamentRoundDeliveryState,
    user_id: int,
) -> None:
    request = delivery_context.request
    context = request.context
    operations = delivery_context.operations
    chat_id = context.telegram_targets.get(user_id)
    existing_message_id = context.participant_rows[user_id].standings_message_id
    target = operations.build_target(
        delivery_context=delivery_context,
        user_id=user_id,
        chat_id=chat_id,
        delivery_operation=operations.delivery_operation(existing_message_id),
        pending_replay_safe=existing_message_id is not None,
    )
    text, keyboard = _build_round_payload(delivery_context, user_id)
    delivery = await operations.prepare_delivery(
        target=target,
        happened_at=delivery_context.happened_at,
    )
    if not delivery.should_send:
        state.skipped += 1
        return
    await operations.begin_dispatch(delivery, happened_at=delivery_context.happened_at)
    attempt = TournamentRoundMessageAttempt(
        user_id=user_id,
        chat_id=chat_id,
        existing_message_id=existing_message_id,
        target=target,
        text=text,
        keyboard=keyboard,
    )
    if existing_message_id is None:
        await send_initial_round_message(
            delivery_context=delivery_context,
            state=state,
            attempt=attempt,
        )
        return
    await edit_or_replace_round_message(
        delivery_context=delivery_context,
        state=state,
        attempt=attempt,
    )


async def deliver_round_messages_with_dependencies(
    *,
    request: TournamentRoundDeliveryRequest,
    operations: TournamentRoundDeliveryOperations,
) -> TournamentRoundDeliveryResult:
    state = TournamentRoundDeliveryState()
    happened_at = datetime.now(timezone.utc)
    flow = "private_tournament_round_messaging"
    task_name = "tournaments_messaging.run_private_tournament_round_messaging"
    correlation_id = str(request.context.parsed_tournament_id)
    content_version = operations.content_version(tournament=request.context.tournament)
    bot = request.build_bot_fn()
    delivery_context = TournamentRoundDeliveryContext(
        request=request,
        operations=operations,
        bot=bot,
        happened_at=happened_at,
        flow=flow,
        task_name=task_name,
        correlation_id=correlation_id,
        content_version=content_version,
    )
    delivery_errors: list[Exception] = []
    try:
        for user_id in request.context.standings_user_ids:
            try:
                await _deliver_user_message(
                    delivery_context=delivery_context,
                    state=state,
                    user_id=user_id,
                )
            except Exception as exc:
                delivery_errors.append(exc)
                continue
    finally:
        await bot.session.close()
    if delivery_errors:
        raise delivery_errors[0]
    return state.to_result()


__all__ = ["deliver_round_messages_with_dependencies"]
