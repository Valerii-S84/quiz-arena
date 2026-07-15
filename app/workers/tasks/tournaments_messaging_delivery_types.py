from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.workers.tasks.tournaments_messaging_context import TournamentRoundMessagingContext


@dataclass(frozen=True, slots=True)
class TournamentRoundDeliveryResult:
    sent: int
    edited: int
    failed: int
    skipped: int
    new_message_ids: dict[int, int]
    replaced_message_ids: dict[int, int]


@dataclass(frozen=True, slots=True)
class TournamentRoundDeliveryRequest:
    context: TournamentRoundMessagingContext
    build_bot_fn: Callable[[], Any]
    resolve_match_context_fn: Callable[..., tuple[str | None, int | None]]
    build_standings_lines_fn: Callable[..., list[str]]
    build_completed_text_fn: Callable[..., str]
    build_round_text_fn: Callable[..., str]
    format_deadline_fn: Callable[..., str]
    build_keyboard_fn: Callable[..., object]
    add_share_button_fn: Callable[..., object]
    build_share_url_fn: Callable[..., str]
    is_message_not_modified_error_fn: Callable[[Exception], bool]
    logger: Any


@dataclass(frozen=True, slots=True)
class TournamentRoundDeliveryOperations:
    prepare_delivery: Callable[..., Any]
    prepare_fallback_delivery: Callable[..., Any]
    begin_dispatch: Callable[..., Any]
    begin_fallback_dispatch: Callable[..., Any]
    mark_failed: Callable[..., Any]
    persist_initial_message: Callable[..., Any]
    persist_edited_message: Callable[..., Any]
    persist_replacement_message: Callable[..., Any]
    mark_fallback_and_original_failed: Callable[..., Any]
    record_original_skipped: Callable[..., Any]
    build_target: Callable[..., Any]
    delivery_operation: Callable[..., str]
    fallback_delivery_operation: Callable[..., str]
    content_version: Callable[..., str]
    build_payload: Callable[..., tuple[str, object]]


@dataclass(frozen=True, slots=True)
class TournamentRoundDeliveryContext:
    request: TournamentRoundDeliveryRequest
    operations: TournamentRoundDeliveryOperations
    bot: Any
    happened_at: datetime
    flow: str
    task_name: str
    correlation_id: str
    content_version: str


@dataclass(frozen=True, slots=True)
class TournamentRoundMessageAttempt:
    user_id: int
    chat_id: int | None
    existing_message_id: int | None
    target: Any
    text: str
    keyboard: object


@dataclass(slots=True)
class TournamentRoundDeliveryState:
    sent: int = 0
    edited: int = 0
    failed: int = 0
    skipped: int = 0
    new_message_ids: dict[int, int] = field(default_factory=dict)
    replaced_message_ids: dict[int, int] = field(default_factory=dict)

    def to_result(self) -> TournamentRoundDeliveryResult:
        return TournamentRoundDeliveryResult(
            sent=self.sent,
            edited=self.edited,
            failed=self.failed,
            skipped=self.skipped,
            new_message_ids=self.new_message_ids,
            replaced_message_ids=self.replaced_message_ids,
        )


__all__ = [
    "TournamentRoundDeliveryContext",
    "TournamentRoundDeliveryOperations",
    "TournamentRoundDeliveryRequest",
    "TournamentRoundDeliveryResult",
    "TournamentRoundDeliveryState",
    "TournamentRoundMessageAttempt",
]
