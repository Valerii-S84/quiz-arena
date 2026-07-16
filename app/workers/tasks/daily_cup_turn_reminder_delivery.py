from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.services.telegram_delivery import deliver_telegram_once


@dataclass(frozen=True, slots=True)
class ReminderItem:
    tournament_id: UUID
    challenge_id: str
    target_user_id: int
    target_chat_id: int
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
    session_local: Any,
    deliver_once: Any | None = None,
) -> ReminderDeliveryResult:
    sent_total = 0
    failed_total = 0
    sent_user_ids_by_tournament: dict[UUID, list[int]] = defaultdict(list)
    resolved_deliver_once = deliver_once if deliver_once is not None else deliver_telegram_once

    bot = build_bot_fn()
    try:
        for reminder in reminders:
            delivered = await _deliver_one_reminder(
                bot=bot,
                reminder=reminder,
                build_keyboard=build_keyboard,
                build_text=build_text,
                logger=logger,
                session_local=session_local,
                deliver_once=resolved_deliver_once,
            )
            if delivered:
                sent_total += 1
                sent_user_ids_by_tournament[reminder.tournament_id].append(reminder.target_user_id)
            else:
                failed_total += 1
    finally:
        await bot.session.close()

    return ReminderDeliveryResult(
        sent_total=sent_total,
        failed_total=failed_total,
        sent_user_ids_by_tournament=sent_user_ids_by_tournament,
    )


async def _deliver_one_reminder(
    *,
    bot: Any,
    reminder: ReminderItem,
    build_keyboard: Callable[..., object],
    build_text: Callable[..., str],
    logger: Any,
    session_local: Any,
    deliver_once: Any,
) -> bool:
    keyboard = _build_reminder_keyboard(reminder=reminder, build_keyboard=build_keyboard)
    text = build_text(opponent_label=reminder.opponent_label, deadline_text=reminder.deadline_text)

    async def _send() -> None:
        await bot.send_message(
            chat_id=reminder.target_chat_id,
            text=text,
            reply_markup=keyboard,
        )

    try:
        outcome = await deliver_once(
            session_local,
            attempt=_turn_reminder_attempt(reminder),
            send=_send,
        )
    except Exception as exc:
        logger.warning(
            "daily_cup_turn_reminder_send_failed",
            challenge_id=reminder.challenge_id,
            user_id=reminder.target_user_id,
            error_type=type(exc).__name__,
        )
        return False
    return outcome.status == "SENT"


def _build_reminder_keyboard(
    *,
    reminder: ReminderItem,
    build_keyboard: Callable[..., object],
) -> object:
    return build_keyboard(
        tournament_id=str(reminder.tournament_id),
        can_join=False,
        play_challenge_id=reminder.challenge_id,
        show_share_result=False,
    )


def _turn_reminder_attempt(reminder: ReminderItem) -> TelegramDeliveryAttemptCreate:
    tournament_id = str(reminder.tournament_id)
    return TelegramDeliveryAttemptCreate(
        flow="daily_cup",
        task_name="daily_cup.turn_reminder",
        correlation_id=f"daily_cup_turn_reminder:{tournament_id}",
        idempotency_key=(
            f"daily_cup:turn_reminder:{tournament_id}:"
            f"{reminder.challenge_id}:{reminder.target_user_id}"
        ),
        target_type="daily_cup_turn_reminder",
        target_id=reminder.challenge_id,
        telegram_user_id=reminder.target_chat_id,
        safe_context={
            "tournament_id": tournament_id,
            "target_user_id": reminder.target_user_id,
        },
    )


__all__ = [
    "ReminderBatch",
    "ReminderDeliveryResult",
    "ReminderItem",
    "deliver_reminders",
    "prepare_reminder_batch",
]
