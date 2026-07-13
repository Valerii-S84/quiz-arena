from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.workers.tasks.daily_cup_turn_reminder_delivery_target import (
    build_turn_reminder_delivery_target,
)
from app.workers.tasks.daily_cup_turn_reminder_delivery_types import (
    ReminderDeliveryDependencies,
    ReminderDeliveryResult,
    ReminderItem,
)


@dataclass(frozen=True, slots=True)
class ReminderDeliveryContext:
    bot: Any
    build_keyboard: Callable[..., object]
    build_text: Callable[..., str]
    logger: Any
    dependencies: ReminderDeliveryDependencies
    happened_at: Any


@dataclass(slots=True)
class ReminderDeliveryState:
    sent_total: int = 0
    failed_total: int = 0
    skipped_total: int = 0
    sent_user_ids_by_tournament: dict[UUID, list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def to_result(self) -> ReminderDeliveryResult:
        return ReminderDeliveryResult(
            sent_total=self.sent_total,
            failed_total=self.failed_total,
            skipped_total=self.skipped_total,
            sent_user_ids_by_tournament=self.sent_user_ids_by_tournament,
        )


async def _send_reminder(
    *,
    bot: Any,
    reminder: ReminderItem,
    keyboard: object,
    text: str,
) -> None:
    await bot.send_message(
        chat_id=reminder.target_chat_id,
        text=text,
        reply_markup=keyboard,
    )


async def _mark_send_failed(
    *,
    dependencies: ReminderDeliveryDependencies,
    idempotency_key: str,
    happened_at: Any,
    exc: Exception,
) -> None:
    await dependencies.mark_telegram_delivery_failed(
        idempotency_key=idempotency_key,
        happened_at=happened_at,
        exc=exc,
    )


async def _deliver_one_reminder(
    *,
    context: ReminderDeliveryContext,
    state: ReminderDeliveryState,
    reminder: ReminderItem,
) -> None:
    target = build_turn_reminder_delivery_target(
        reminder=reminder,
        build_delivery_idempotency_key_fn=context.dependencies.build_delivery_idempotency_key,
    )
    delivery = await context.dependencies.prepare_telegram_delivery(
        target=target, happened_at=context.happened_at
    )
    if not delivery.should_send:
        state.skipped_total += 1
        return
    keyboard = context.build_keyboard(
        tournament_id=str(reminder.tournament_id),
        can_join=False,
        play_challenge_id=reminder.challenge_id,
        show_share_result=False,
    )
    text = context.build_text(
        opponent_label=reminder.opponent_label,
        deadline_text=reminder.deadline_text,
    )
    await context.dependencies.begin_telegram_delivery_dispatch(
        delivery, happened_at=context.happened_at
    )
    try:
        await _send_reminder(bot=context.bot, reminder=reminder, keyboard=keyboard, text=text)
        state.sent_total += 1
        state.sent_user_ids_by_tournament[reminder.tournament_id].append(reminder.target_user_id)
    except Exception as exc:
        await _mark_send_failed(
            dependencies=context.dependencies,
            idempotency_key=target.idempotency_key,
            happened_at=context.happened_at,
            exc=exc,
        )
        context.logger.warning(
            "daily_cup_turn_reminder_send_failed",
            challenge_id=reminder.challenge_id,
            user_id=reminder.target_user_id,
            error_type=type(exc).__name__,
        )
        state.failed_total += 1
        return
    await context.dependencies.mark_telegram_delivery_sent(
        idempotency_key=target.idempotency_key,
        happened_at=context.happened_at,
    )


async def deliver_reminders_with_dependencies(
    *,
    reminders: list[ReminderItem],
    build_bot_fn: Callable[[], Any],
    build_keyboard: Callable[..., object],
    build_text: Callable[..., str],
    logger: Any,
    dependencies: ReminderDeliveryDependencies,
) -> ReminderDeliveryResult:
    bot = build_bot_fn()
    context = ReminderDeliveryContext(
        bot=bot,
        build_keyboard=build_keyboard,
        build_text=build_text,
        logger=logger,
        dependencies=dependencies,
        happened_at=dependencies.happened_at(),
    )
    state = ReminderDeliveryState()
    try:
        for reminder in reminders:
            await _deliver_one_reminder(context=context, state=state, reminder=reminder)
    finally:
        await bot.session.close()
    return state.to_result()


__all__ = ["deliver_reminders_with_dependencies"]
