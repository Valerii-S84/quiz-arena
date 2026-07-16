from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TelegramDeliveryAttemptCreate:
    flow: str
    task_name: str
    correlation_id: str
    idempotency_key: str
    target_type: str
    target_id: str
    telegram_user_id: int | None = None
    chat_id_hash: str | None = None
    safe_context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TelegramDeliveryFailure:
    failure_code: str
    failure_reason: str | None = None
    telegram_error_code: int | None = None
    is_blocked_candidate: bool = False
