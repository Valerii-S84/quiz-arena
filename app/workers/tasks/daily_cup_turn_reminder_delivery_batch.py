from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.workers.tasks.daily_cup_turn_reminder_delivery_types import ReminderBatch, ReminderItem


@dataclass(frozen=True, slots=True)
class ReminderPreparationContext:
    now_utc_value: datetime
    user_labels: dict[int, str]
    telegram_targets: dict[int, int]
    resolve_turn_reminder_users_fn: Callable[..., tuple[tuple[int, int], ...]]
    resolve_opponent_label_fn: Callable[..., str]
    format_deadline_fn: Callable[..., str]


@dataclass(frozen=True, slots=True)
class ReminderBatchPreparationRequest:
    candidates: list[tuple[Any, Any]]
    now_utc_value: datetime
    format_user_label_fn: Callable[..., str]
    list_users_by_ids: Callable[..., Awaitable[list[Any]]]
    session: Any
    resolve_turn_reminder_users_fn: Callable[..., tuple[tuple[int, int], ...]]
    resolve_opponent_label_fn: Callable[..., str]
    format_deadline_fn: Callable[..., str]


async def prepare_reminder_batch(
    *,
    request: ReminderBatchPreparationRequest,
) -> ReminderBatch:
    participant_user_ids = _collect_participant_user_ids(
        candidates=request.candidates,
        resolve_turn_reminder_users_fn=request.resolve_turn_reminder_users_fn,
    )
    users = await request.list_users_by_ids(request.session, list(participant_user_ids))
    user_labels = {
        int(user.id): request.format_user_label_fn(
            username=user.username, first_name=user.first_name
        )
        for user in users
    }
    context = ReminderPreparationContext(
        now_utc_value=request.now_utc_value,
        user_labels=user_labels,
        telegram_targets={int(user.id): int(user.telegram_user_id) for user in users},
        resolve_turn_reminder_users_fn=request.resolve_turn_reminder_users_fn,
        resolve_opponent_label_fn=request.resolve_opponent_label_fn,
        format_deadline_fn=request.format_deadline_fn,
    )
    reminders: list[ReminderItem] = []
    queued_target_keys: set[tuple[Any, int]] = set()
    scanned_total = 0
    skipped_total = 0
    for match, challenge in request.candidates:
        scanned_total += 1
        window_key = _window_key(challenge.expires_last_chance_notified_at)
        challenge.expires_last_chance_notified_at = request.now_utc_value
        challenge.updated_at = request.now_utc_value

        skipped_total += _queue_candidate_reminders(
            match=match,
            challenge=challenge,
            window_key=window_key,
            context=context,
            reminders=reminders,
            queued_target_keys=queued_target_keys,
        )

    return ReminderBatch(
        reminders=reminders,
        scanned_total=scanned_total,
        skipped_total=skipped_total,
    )


def _collect_participant_user_ids(
    *,
    candidates: list[tuple[Any, Any]],
    resolve_turn_reminder_users_fn: Callable[..., tuple[tuple[int, int], ...]],
) -> set[int]:
    participant_user_ids: set[int] = set()
    for _match, challenge in candidates:
        resolved_users = resolve_turn_reminder_users_fn(challenge=challenge)
        for target_user_id, opponent_user_id in resolved_users:
            participant_user_ids.add(target_user_id)
            participant_user_ids.add(opponent_user_id)
    return participant_user_ids


def _queue_candidate_reminders(
    *,
    match: Any,
    challenge: Any,
    window_key: str,
    context: ReminderPreparationContext,
    reminders: list[ReminderItem],
    queued_target_keys: set[tuple[Any, int]],
) -> int:
    skipped_total = 0
    resolved_users = context.resolve_turn_reminder_users_fn(challenge=challenge)
    if not resolved_users:
        return 1
    for target_user_id, opponent_user_id in resolved_users:
        target_chat_id = context.telegram_targets.get(target_user_id)
        if target_chat_id is None:
            skipped_total += 1
            continue
        target_key = (match.tournament_id, target_user_id)
        if target_key in queued_target_keys:
            skipped_total += 1
            continue
        queued_target_keys.add(target_key)
        reminders.append(
            _build_reminder_item(
                match=match,
                challenge=challenge,
                target_user_id=target_user_id,
                target_chat_id=target_chat_id,
                opponent_user_id=opponent_user_id,
                window_key=window_key,
                context=context,
            )
        )
    return skipped_total


def _build_reminder_item(
    *,
    match: Any,
    challenge: Any,
    target_user_id: int,
    target_chat_id: int,
    opponent_user_id: int,
    window_key: str,
    context: ReminderPreparationContext,
) -> ReminderItem:
    return ReminderItem(
        tournament_id=match.tournament_id,
        challenge_id=str(challenge.id),
        target_user_id=target_user_id,
        target_chat_id=target_chat_id,
        window_key=window_key,
        opponent_label=context.resolve_opponent_label_fn(
            target_user_id=target_user_id,
            opponent_user_id=opponent_user_id,
            user_labels=context.user_labels,
        ),
        deadline_text=context.format_deadline_fn(match.deadline),
    )


def _window_key(value: datetime | None) -> str:
    if value is None:
        return "initial"
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["ReminderBatchPreparationRequest", "prepare_reminder_batch"]
