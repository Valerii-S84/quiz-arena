from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.services.telegram_delivery import (
    TelegramDeliveryTarget,
    begin_telegram_delivery_dispatch,
    build_delivery_idempotency_key,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)


@dataclass(frozen=True, slots=True)
class ReminderItem:
    tournament_id: UUID
    challenge_id: str
    target_user_id: int
    target_chat_id: int
    window_key: str
    opponent_label: str
    deadline_text: str


@dataclass(frozen=True, slots=True)
class ReminderBatch:
    reminders: list[ReminderItem]
    scanned_total: int
    skipped_total: int


@dataclass(frozen=True, slots=True)
class ReminderDeliveryResult:
    sent_total: int
    failed_total: int
    skipped_total: int
    sent_user_ids_by_tournament: dict[UUID, list[int]]


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
    participant_user_ids: set[int] = set()
    for _match, challenge in candidates:
        resolved_users = resolve_turn_reminder_users_fn(challenge=challenge)
        for target_user_id, opponent_user_id in resolved_users:
            participant_user_ids.add(target_user_id)
            participant_user_ids.add(opponent_user_id)

    users = await list_users_by_ids(session, list(participant_user_ids))
    user_labels = {
        int(user.id): format_user_label_fn(username=user.username, first_name=user.first_name)
        for user in users
    }
    telegram_targets = {int(user.id): int(user.telegram_user_id) for user in users}
    reminders: list[ReminderItem] = []
    queued_target_keys: set[tuple[UUID, int]] = set()
    scanned_total = 0
    skipped_total = 0
    for match, challenge in candidates:
        scanned_total += 1
        window_key = _window_key(challenge.expires_last_chance_notified_at)
        challenge.expires_last_chance_notified_at = now_utc_value
        challenge.updated_at = now_utc_value

        resolved_users = resolve_turn_reminder_users_fn(challenge=challenge)
        if not resolved_users:
            skipped_total += 1
            continue
        for target_user_id, opponent_user_id in resolved_users:
            target_chat_id = telegram_targets.get(target_user_id)
            if target_chat_id is None:
                skipped_total += 1
                continue
            target_key = (match.tournament_id, target_user_id)
            if target_key in queued_target_keys:
                skipped_total += 1
                continue
            queued_target_keys.add(target_key)
            reminders.append(
                ReminderItem(
                    tournament_id=match.tournament_id,
                    challenge_id=str(challenge.id),
                    target_user_id=target_user_id,
                    target_chat_id=target_chat_id,
                    window_key=window_key,
                    opponent_label=resolve_opponent_label_fn(
                        target_user_id=target_user_id,
                        opponent_user_id=opponent_user_id,
                        user_labels=user_labels,
                    ),
                    deadline_text=format_deadline_fn(match.deadline),
                )
            )

    return ReminderBatch(
        reminders=reminders,
        scanned_total=scanned_total,
        skipped_total=skipped_total,
    )


async def deliver_reminders(
    *,
    reminders: list[ReminderItem],
    build_bot_fn: Callable[[], Any],
    build_keyboard: Callable[..., object],
    build_text: Callable[..., str],
    logger: Any,
) -> ReminderDeliveryResult:
    sent_total = 0
    failed_total = 0
    skipped_total = 0
    sent_user_ids_by_tournament: dict[UUID, list[int]] = defaultdict(list)
    happened_at = datetime.now(timezone.utc)

    bot = build_bot_fn()
    try:
        for reminder in reminders:
            target = _turn_reminder_delivery_target(reminder=reminder)
            delivery = await prepare_telegram_delivery(target=target, happened_at=happened_at)
            if not delivery.should_send:
                skipped_total += 1
                continue
            keyboard = build_keyboard(
                tournament_id=str(reminder.tournament_id),
                can_join=False,
                play_challenge_id=reminder.challenge_id,
                show_share_result=False,
            )
            text = build_text(
                opponent_label=reminder.opponent_label,
                deadline_text=reminder.deadline_text,
            )
            await begin_telegram_delivery_dispatch(delivery, happened_at=happened_at)
            try:
                await bot.send_message(
                    chat_id=reminder.target_chat_id,
                    text=text,
                    reply_markup=keyboard,
                )
                sent_total += 1
                sent_user_ids_by_tournament[reminder.tournament_id].append(reminder.target_user_id)
            except Exception as exc:
                await mark_telegram_delivery_failed(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                    exc=exc,
                )
                logger.warning(
                    "daily_cup_turn_reminder_send_failed",
                    challenge_id=reminder.challenge_id,
                    user_id=reminder.target_user_id,
                    error_type=type(exc).__name__,
                )
                failed_total += 1
                continue
            await mark_telegram_delivery_sent(
                idempotency_key=target.idempotency_key,
                happened_at=happened_at,
            )
    finally:
        await bot.session.close()

    return ReminderDeliveryResult(
        sent_total=sent_total,
        failed_total=failed_total,
        skipped_total=skipped_total,
        sent_user_ids_by_tournament=sent_user_ids_by_tournament,
    )


def _turn_reminder_delivery_target(*, reminder: ReminderItem) -> TelegramDeliveryTarget:
    target_id = f"{reminder.challenge_id}:{reminder.target_user_id}:{reminder.window_key}"
    correlation_id = str(reminder.tournament_id)
    return TelegramDeliveryTarget(
        flow="daily_cup_turn_reminder",
        task_name="daily_cup.send_turn_reminders",
        correlation_id=correlation_id,
        target_type="challenge_user",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow="daily_cup_turn_reminder",
            correlation_id=correlation_id,
            target_type="challenge_user",
            target_id=target_id,
        ),
        telegram_user_id=reminder.target_chat_id,
        chat_id=reminder.target_chat_id,
        safe_context={
            "tournament_id": correlation_id,
            "challenge_id": reminder.challenge_id,
            "target_user_id": reminder.target_user_id,
            "window_key": reminder.window_key,
        },
    )


def _window_key(value: datetime | None) -> str:
    if value is None:
        return "initial"
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


__all__ = "ReminderBatch ReminderDeliveryResult ReminderItem deliver_reminders prepare_reminder_batch".split()
