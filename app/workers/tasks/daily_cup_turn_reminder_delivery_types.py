from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


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
    challenge_rows: list[Any]
    challenge_ids: set[str]


@dataclass(frozen=True, slots=True)
class ReminderDeliveryResult:
    sent_total: int
    failed_total: int
    skipped_total: int
    sent_user_ids_by_tournament: dict[UUID, list[int]]
    failed_challenge_ids: set[str]
    system_errors: tuple[Exception, ...]


@dataclass(frozen=True, slots=True)
class ReminderDeliveryDependencies:
    prepare_telegram_delivery: Callable[..., Awaitable[Any]]
    begin_telegram_delivery_dispatch: Callable[..., Awaitable[Any]]
    mark_telegram_delivery_failed: Callable[..., Awaitable[Any]]
    mark_telegram_delivery_sent: Callable[..., Awaitable[Any]]
    build_delivery_idempotency_key: Callable[..., str]
    happened_at: Callable[[], datetime]


__all__ = [
    "ReminderBatch",
    "ReminderDeliveryDependencies",
    "ReminderDeliveryResult",
    "ReminderItem",
]
